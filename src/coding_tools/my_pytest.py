# src/coding_tools/my_pytest.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
#
from dataclasses import replace
from pathlib import Path

from coding_tools import file_handler, my_logger, my_subprocess
from coding_tools.my_run import EditState, RunOutput, RunState
from coding_tools.my_subprocess import CmdParams

logger = my_logger.logger(__name__)

HEADER_ERRORS = (
    "=========================================================== "
    "ERRORS ==========================================================="
)
HEADER_FAILURES = (
    "=========================================================== "
    "FAILURES ==========================================================="
)
HEADER_WARNINGS = (
    "====================================================== "
    "warnings summary ======================================================="
)
FOOT_START = "\n========================================================"
CMD = (
    "uv run pytest --import-mode=importlib --cov=MODULE_PATH --cov-branch "
    "--cov-report=term-missing --cov-report=annotate:.coverage_annotations "
    "UNIT_TEST_PATH"
)
FUNC_NAME = "Pytest"
MIN_PARTS_BAD_LOG = 2


def clean_log(txt: str) -> str:
    """Clear running info that don't give tips on pytest errors, fail, warnings."""
    if HEADER_ERRORS in txt:
        header = HEADER_ERRORS
    elif HEADER_FAILURES in txt:
        header = HEADER_FAILURES
    elif HEADER_WARNINGS in txt:
        header = HEADER_WARNINGS
    else:
        return ""

    parts = txt.split(header)
    if len(parts) < MIN_PARTS_BAD_LOG:
        return ""

    sub_txt = parts[1]
    end_parts = sub_txt.split(FOOT_START)

    return f"{header}\n{end_parts[0].strip()}"


def check_edited(out: str, err: str) -> EditState:  # noqa: ARG001
    """Check whether file has been edited."""
    return EditState.KEPT


def check_result(
    out: str,
    err: str,
    exit_code: int,
    run_output: RunOutput,
) -> RunOutput:
    """Check the result of the command run."""
    func = __name__
    return replace(
        run_output,
        status=(RunState.PASS if exit_code == 0 else RunState.FAIL),
        sub_func=func,
        edited=check_edited(out, err),
    )


def run(file_path: Path | str, run_output: RunOutput) -> RunOutput:

    params = CmdParams(
        check_result=check_result,
        clean_log=None,
        func_name=FUNC_NAME,
        log_path=file_handler.get_pytest_log_path(file_path),
        input_path=file_path,
    )
    return my_subprocess.run(cmd=CMD, params=params, run_output=run_output)
