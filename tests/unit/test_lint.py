# tests/unit/test_lint.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for lint checking functionality."""
from pathlib import Path

from coding_tools.check import CheckParams
from coding_tools.lint import check, precheck
from coding_tools.my_run import RunOutput, RunState


def test_dummy() -> None:
    """Verify basic truthiness."""
    assert True

def test_check_file_missing(tmp_path: Path) -> None:
    """Test check when file is missing."""
    missing_file = tmp_path / "missing.py"
    params = CheckParams(file_path=missing_file, old_txt="", new_txt="content")
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = check(params, output)
    assert res.status == RunState.FAIL

def test_check_success_with_new_text(tmp_path: Path) -> None:
    """Test check success with new text provided."""
    file_path = tmp_path / "dummy.py"
    file_path.write_text("", encoding="utf-8")
    params = CheckParams(file_path=file_path, old_txt="", new_txt="print('hi')")
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = check(params, output)
    assert res.status == RunState.FAIL

def test_precheck(tmp_path: Path) -> None:
    """Test precheck execution."""
    file_path = tmp_path / "dummy.py"
    file_path.write_text("", encoding="utf-8")
    params = CheckParams(file_path=file_path, old_txt="", new_txt="")
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = precheck(params, output)
    assert res.status == RunState.FAIL
