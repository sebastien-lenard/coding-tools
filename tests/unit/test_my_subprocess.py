# tests/unit/test_my_subprocess.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Test my_subprocess module."""
from pathlib import Path

from coding_tools.my_run import RunOutput, RunState
from coding_tools.my_subprocess import CmdParams, run


def replace_ro(ro: RunOutput, code: int) -> RunOutput:
    """Replace run output status based on return code."""
    return RunOutput(
        func="test",
        status=RunState.PASS if code == 0 else RunState.FAIL,
    )


def test_run_subprocess(tmp_path: Path) -> None:
    """Test running subprocess with input path."""
    input_path = tmp_path / "input.py"
    input_path.write_text("print('hello')", encoding="utf-8")
    log_path = tmp_path / "log.txt"
    params = CmdParams(
        check_result=lambda stdout, stderr, code, ro: replace_ro(ro, code),
        clean_log=None,
        func_name="test_func",
        log_path=log_path,
        input_path=input_path,
    )
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    res = run("python INPUT_PATH LOG_PATH", params, run_output)
    assert res.status == RunState.PASS


def test_run_subprocess_with_log_in_cmd(tmp_path: Path) -> None:
    """Test running subprocess with log in command."""
    input_path = tmp_path / "input.py"
    input_path.write_text("print('hello')", encoding="utf-8")
    log_path = tmp_path / "log.txt"
    params = CmdParams(
        check_result=lambda stdout, stderr, code, ro: replace_ro(ro, code),
        clean_log=None,
        func_name="test_func",
        log_path=log_path,
        input_path=input_path,
    )
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    res = run("python -c 'print(1)'", params, run_output)
    assert res.status == RunState.PASS
