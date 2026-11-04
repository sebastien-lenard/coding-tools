# tests/unit/test_docstring.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for docstring module."""

from pathlib import Path

from coding_tools.check import CheckParams
from coding_tools.docstring import check, precheck
from coding_tools.my_run import RunOutput, RunState


def test_check_empty_old_txt() -> None:
    """Test check with empty old_txt."""
    params = CheckParams(
        file_path=Path("dummy.py"), old_txt="", new_txt="print('hello')",
    )
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    result = check(params, run_output)
    assert result.status == RunState.FAIL
    assert "Empty original text" in result.msg


def test_check_empty_new_txt() -> None:
    """Test check with empty new_txt."""
    params = CheckParams(
        file_path=Path("dummy.py"), old_txt="print('hello')", new_txt="",
    )
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    result = check(params, run_output)
    assert result.status == RunState.FAIL
    assert "Empty new text" in result.msg


def test_check_success() -> None:
    """Test check success when codes match structurally."""
    params = CheckParams(
        file_path=Path("dummy.py"), old_txt="print('hello')", new_txt="print('hello')",
    )
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    result = check(params, run_output)
    assert result.status != RunState.FAIL


def test_precheck() -> None:
    """Test precheck behavior."""
    params = CheckParams(file_path=Path("dummy.py"), old_txt="", new_txt="")
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    result = precheck(params, run_output)
    assert result.status == RunState.SKIP
