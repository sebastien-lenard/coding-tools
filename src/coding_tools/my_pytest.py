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

FUNC_NAME = "Pytest"
CMD = (
    "uv run pytest --import-mode=importlib --cov=MODULE_PATH --cov-branch "
    "--cov-report=term-missing --cov-report=annotate:.coverage_annotations "
    "UNIT_TEST_PATH"
)


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
