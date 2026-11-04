# src/coding_tools/my_pyright.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Run basedpyright and check output logs.

Runs basedpyright via uv. Save log to file. Clean path strings.
"""

import re
from dataclasses import replace
from pathlib import Path

from coding_tools import my_logger, my_path, my_subprocess
from coding_tools.my_run import EditState, RunOutput, RunState
from coding_tools.my_subprocess import CmdParams

logger = my_logger.logger(__name__)

CLEAR_PATHS = r"(?:[a-zA-Z]:\|[.\/])[^\s]*?\.py(?::\d+:\d+)?"
CMD = "uv run basedpyright INPUT_PATH"
FUNC_NAME = "Based-Pyright"


def check_edited(out: str, err: str) -> EditState:  # noqa: ARG001
    """Check if file got edit state and keep.

    Pass out and err. Return EditState.KEPT.
    """
    return EditState.KEPT


def check_result(
    out:
    str,
    err:
    str,
    exit_code:
    int,
    run_output:
    RunOutput,
) -> RunOutput:
    """Check run exit code and set pass or fail state.

    Returns RunOutput with state and sub func set. Exit code 0 means pass.
    """
    func = __name__
    return replace(
        run_output,
        status=(RunState.PASS if exit_code == 0 else RunState.FAIL),
        sub_func=func,
        edited=check_edited(out, err),
    )


def clean_log(txt: str) -> str:
    """Clear run path info from log text.

    Regex sub on CLEAR_PATHS pattern. Input txt, output clean str.
    """
    return re.sub(CLEAR_PATHS, "", txt)


def run(file_path: Path | str, run_output: RunOutput) -> RunOutput:
    """Run basedpyright via uv and save output to log.

    Uses CmdParams and my_subprocess.run. Needs uv and basedpyright CLI tool.
    """
    params = CmdParams(
        check_result=check_result,
        clean_log=clean_log,
        func_name=FUNC_NAME,
        log_path=my_path.get_basedpyright_log_path(file_path),
        input_path=file_path,
    )
    return my_subprocess.run(cmd=CMD, params=params, run_output=run_output)
