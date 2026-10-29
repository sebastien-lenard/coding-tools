# src/coding_tools/my_ruff.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
import re
import subprocess
from dataclasses import replace
from pathlib import Path

from coding_tools import file_handler, my_logger, my_subprocess
from coding_tools.my_run import EditState, RunOutput, RunState
from coding_tools.my_subprocess import CmdParams

logger = my_logger.logger(__name__)

FIXED_MSG = r"Found \d+ errors \(\d+ fixed"
FUNC_NAME = "Ruff"
CMD = "uv run ruff check INPUT_PATH --fix"


def check_edited(out: str, err: str) -> EditState:
    """Check whether file has been edited."""
    return EditState.EDITED if (re.search(FIXED_MSG, f"{out}{err}")) else EditState.KEPT


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


def clean_log(txt: str) -> str:
    """Clear running info that don't give tips on lint issues."""
    lines = [
        line
        for line in txt.splitlines()
        if not line.strip().lower().startswith("warning:")
    ]
    return "\n".join(lines)


def run(file_path: Path | str, run_output: RunOutput) -> RunOutput:
    """Run ruff check with fix option and save output to log.

    Uses uv and ruff check.
    """
    params = CmdParams(
        check_result=check_result,
        clean_log=clean_log,
        func_name=FUNC_NAME,
        log_path=file_handler.get_ruff_log_path(file_path),
        input_path=file_path,
    )
    return my_subprocess.run(cmd=CMD, params=params, run_output=run_output)


def no_docstring_files(path: Path | str) -> list[Path]:
    """TOSEE."""
    cmd_list = [
        "uv",
        "run",
        "ruff",
        "check",
        str(path),
        "--select D1",
        "--output-format github",
    ]
    cmd_str = " ".join(cmd_list)
    logger.progress(None, f"Run `{cmd_str}`")

    txt = subprocess.run(  # noqa: S603
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    files = set()
    for line in txt.stdout.splitlines():
        if ":" in line:
            parts = line.split(":")
            file_str = parts[0].strip()
            if file_str.endswith(".py"):
                files.add(Path(file_str))

    return list(files)
