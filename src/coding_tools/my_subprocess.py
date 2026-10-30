# src/coding_tools/my_subprocess.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from coding_tools import file_handler, my_io, my_logger, my_string
from coding_tools.my_run import EditState, RunOutput

logger = my_logger.logger(__name__)


@dataclass
class CmdParams:
    """Params to run a command and check outcome."""

    check_result: Callable[[str, str, int, RunOutput], RunOutput]
    clean_log: Callable[[str], str] | None
    func_name: str
    log_path: Path | str
    input_path: Path | str | None = None
    output_path: Path | str | None = None


def run(cmd: str, params: CmdParams, run_output: RunOutput) -> RunOutput:
    try:
        module_path = file_handler.module_path(params.input_path)
    except ValueError:
        module_path = ""
    try:
        unit_test_path = file_handler.unit_test_path(params.input_path)[0]
    except ValueError:
        unit_test_path = ""
    swaps = {
        "INPUT_PATH": my_string.my_str(params.input_path),
        "LOG_PATH": my_string.my_str(params.log_path),
        "MODULE_PATH": my_string.my_str(module_path),
        "OUTPUT_PATH": my_string.my_str(params.output_path),
        "UNIT_TEST_PATH": my_string.my_str(unit_test_path),
    }
    log_path_in_cmd = re.search("LOG_PATH", cmd)
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, swaps.keys())) + r")\b")
    cmd = pattern.sub(lambda match: swaps[match.group(0)], cmd)
    logger.progress(None, f"Run `{cmd}`")

    result = subprocess.run(  # noqa: S603
        cmd.split(),
        capture_output=True,
        text=True,
        check=False,
    )

    output_log = f"$ {cmd}\n{result.stdout}\n{result.stderr}"
    if not log_path_in_cmd:
        my_io.write_txt(output_log, params.log_path)
    run_output = params.check_result(
        result.stdout,
        result.stderr,
        result.returncode,
        run_output,
    )

    msg_1 = f"{run_output.status.value}"
    msg_2 = ", fixes saved in" if run_output.edited == EditState.EDITED else ""
    msg = f"{msg_1}{msg_2}" if msg_1 and msg_2 else f"{msg_1}"
    msg = (
        f"{msg} {Path(my_string.my_str(params.input_path)).name}"
        if params.input_path
        else ""
    )
    msg = (
        f"{msg} -> {Path(my_string.my_str(params.output_path)).name}"
        if params.output_path
        else ""
    )

    logger.end(params.func_name, msg)
    return replace(
        run_output,
        msg=msg,
        brief=params.clean_log(output_log) if params.clean_log else output_log,
    )
