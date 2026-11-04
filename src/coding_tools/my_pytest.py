# src/coding_tools/my_pytest.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Run pytest and log test stats.

Uses uv run pytest with branch cov and annotate options. Save output to log.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Final

from coding_tools import my_logger, my_path, my_subprocess
from coding_tools.my_run import EditState, RunOutput, RunState
from coding_tools.my_subprocess import CmdParams

logger = my_logger.logger(__name__)

COVERAGE_HEADER: Final[str] = "tests coverage"
SUMMARY_HEADER: Final[str] = "short test summary info"
CMD: Final[str] = (
    "uv run pytest --import-mode=importlib --cov=MODULE_PATH --cov-branch "
    "--cov-report=term-missing --cov-report=annotate:.coverage_annotations "
    "UNIT_TEST_PATH"
)
FUNC_NAME: Final[str] = "Pytest"

_TRACE_PAT: Final[re.Pattern[str]] = re.compile(
    r"^([^\s:]+\.py):(\d+):\s+in\s+([a-z_][a-z0-9_]*)$",
    re.MULTILINE,
)
_BLOCK_SEP: Final[str] = (
    "_________________________________________________________________________________"
)
_BLOCK_ALT: Final[str] = "__________________________ "

LOG_CALL_TAG: Final[str] = "Captured log call"
LOG_CALL_SEP: Final[str] = (
    f"------------------------------ {LOG_CALL_TAG} ------------------------------"
)

EXC_CAUSE_SEP: Final[str] = "The above exception was the direct cause"


def _extract_file_path_from_log(log: str) -> Path | None:
    """Extract unit test path from the command line header in the log."""
    first_line = log.splitlines()[0] if log.splitlines() else ""
    if "pytest" in first_line:
        parts = first_line.split()
        for part in reversed(parts):
            if part.endswith(".py") and "test_" in part:
                return Path(part)
    return None


def clean_log(txt: str) -> str:
    """Trim run log and inject external module call tips if found."""
    cleaned = txt
    if COVERAGE_HEADER in cleaned:
        cleaned = cleaned.split(COVERAGE_HEADER)[0]
    if SUMMARY_HEADER in cleaned:
        cleaned = cleaned.split(SUMMARY_HEADER)[0]

    for marker in ("FAILURES", "ERRORS", "warnings summary"):
        if marker in cleaned:
            parts = cleaned.split(marker, 1)
            first_part = parts[0].splitlines()[-1] if parts[0].splitlines() else ""
            cleaned = f"{first_part}\n{marker}{parts[1].strip()}"
            break

    success, msg = other_mods_called(txt)
    if success and msg:
        return msg

    return cleaned.strip()


def _strip_block_noise(block: str) -> str:
    """Strip log calls and exception causes from traceback block."""
    if LOG_CALL_SEP in block:
        block = block.split(LOG_CALL_SEP, maxsplit=1)[-1]

    if EXC_CAUSE_SEP in block:
        block = block.split(EXC_CAUSE_SEP)[-1]

    return block.strip()


def _find_external_match(block: str, target_mod_path: str) -> re.Match[str] | None:
    """Find last trace match that is neither a test nor the target module."""
    matches = list(_TRACE_PAT.finditer(block))
    valid_matches = []
    for m in matches:
        file_part = Path(m.group(1)).resolve().as_posix().lower()
        if "tests/" in file_part:
            continue
        if target_mod_path and file_part == target_mod_path:
            continue
        valid_matches.append(m)

    if not valid_matches:
        return None

    return valid_matches[-1]


def _format_external_match(block: str, match: re.Match[str]) -> str:
    """Format snippet for the external function call."""
    ext_file = match.group(1)
    ext_line = match.group(2)
    ext_func = match.group(3)

    lines = []
    for line in block.strip().splitlines():
        if f"in {ext_func}" in line:
            break
        lines.append(line)

    called_by_snippet = "\n".join(lines).strip()
    return (
        f"- Function {ext_func} ({ext_file}:{ext_line})\n"
        f"- Called by:\n{called_by_snippet}\n"
        f"- Fix: Mock call of this function using monkeypatch:\n\n"
    )


def _process_block(block: str, target_mod_path: str) -> str | None:
    """Process a single traceback block."""
    clean_block = _strip_block_noise(block)
    external_match = _find_external_match(clean_block, target_mod_path)
    if not external_match:
        return None

    return _format_external_match(clean_block, external_match)


def _resolve_target_mod_path(test_path: Path) -> str:
    """Resolve absolute lowercase source path for unit test path."""
    try:
        return my_path.src_path(test_path).resolve().as_posix().lower()
    except OSError:
        return ""


def other_mods_called(log: str) -> tuple[bool, str]:
    """Spot calls to other modules in pytest traceback logs.

    Extract blocks and return tuple of flag and format text.
    """
    test_path = _extract_file_path_from_log(log)
    if not test_path:
        return False, ""

    target_mod_path = _resolve_target_mod_path(test_path)

    blocks = log.split(_BLOCK_SEP)
    if len(blocks) <= 1:
        blocks = log.split(_BLOCK_ALT)

    items: list[str] = []

    for block in blocks:
        res = _process_block(block, target_mod_path)
        if res:
            items.append(res)

    if not items:
        return False, ""

    msg = "".join(items)
    return True, msg


def check_edited(out: str, err: str) -> EditState:  # noqa: ARG001
    """Check if test run edit file.

    Always yield KEPT state.
    """
    return EditState.KEPT


def check_result(
    out: str,
    err: str,
    exit_code: int,
    run_output: RunOutput,
) -> RunOutput:
    """Map exit code to RunState pass or fail.

    Set sub func name and edit state in run output dataclass.
    """
    func = __name__
    return replace(
        run_output,
        status=(RunState.PASS if exit_code == 0 else RunState.FAIL),
        sub_func=func,
        edited=check_edited(out, err),
    )


def run(file_path: Path | str, run_output: RunOutput) -> RunOutput:
    """Run pytest on file path via subprocess.

    Set up cmd params with log path and run output. Call sub process run.
    """
    params = CmdParams(
        check_result=check_result,
        clean_log=clean_log,
        func_name=FUNC_NAME,
        log_path=my_path.get_pytest_log_path(file_path),
        input_path=file_path,
    )
    return my_subprocess.run(cmd=CMD, params=params, run_output=run_output)
