# tests/unit/test_static_type.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for static type checking."""

from pathlib import Path

from coding_tools.check import CheckParams
from coding_tools.my_run import RunOutput, RunState
from coding_tools.static_type import check, precheck


def test_check_success_with_new_text(tmp_path: Path) -> None:
    """Test successful check with new text."""
    file_path = tmp_path / "file.py"
    file_path.write_text("x = 1", encoding="utf-8")
    params = CheckParams(file_path=file_path, old_txt="x = 1", new_txt="x = 2")
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    res = check(params, run_output)
    assert res is not None


def test_check_bad_file(tmp_path: Path) -> None:
    """Test check with a missing file."""
    file_path = tmp_path / "missing.py"
    params = CheckParams(file_path=file_path, old_txt="", new_txt="")
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    res = check(params, run_output)
    assert res.status == RunState.FAIL


def test_precheck(tmp_path: Path) -> None:
    """Test precheck functionality."""
    file_path = tmp_path / "file.py"
    file_path.write_text("x = 1", encoding="utf-8")
    params = CheckParams(file_path=file_path, old_txt="x = 1", new_txt="")
    run_output = RunOutput(func="test", status=RunState.PRESTART)
    res = precheck(params, run_output)
    assert res is not None
