# tests/unit/test_unit_test.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for unit_test module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coding_tools.check import CheckParams
from coding_tools.my_run import RunOutput, RunState
from coding_tools.unit_test import check, precheck


def test_dummy() -> None:
    """Test dummy assertion."""
    true_val = 1
    assert true_val == 1


def test_check_bad_file(tmp_path: Path) -> None:
    """Test check function with missing file."""
    f = tmp_path / "missing.py"
    params = CheckParams(file_path=f, old_txt="", new_txt="")
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = check(params, output)
    assert res.status == RunState.FAIL


@patch("coding_tools.my_path.src_path")
def test_check_success(mock_src_path: MagicMock, tmp_path: Path) -> None:
    """Test check function success."""
    f = tmp_path / "file.py"
    f.write_text("print(1)", encoding="utf-8")
    mock_src_path.return_value = f
    params = CheckParams(file_path=f, old_txt="print(1)", new_txt="print(2)")
    output = RunOutput(func="test", status=RunState.PRESTART)

    with patch("coding_tools.my_pytest.run") as mock_pytest_run, \
         patch("coding_tools.pytest_cov.run") as mock_cov_run:
        mock_pytest_run.return_value = RunOutput(func="test", status=RunState.PASS)
        mock_cov_run.return_value = RunOutput(func="test", status=RunState.PASS)
        res = check(params, output)
        assert res.status == RunState.PASS


@patch("coding_tools.my_path.src_path")
def test_precheck(mock_src_path: MagicMock, tmp_path: Path) -> None:
    """Test precheck function success."""
    f = tmp_path / "file.py"
    f.write_text("print(1)", encoding="utf-8")
    mock_src_path.return_value = f
    params = CheckParams(file_path=f, old_txt="print(1)", new_txt="print(2)")
    output = RunOutput(func="test", status=RunState.PRESTART)

    with patch("coding_tools.my_pytest.run") as mock_pytest_run, \
         patch("coding_tools.pytest_cov.run") as mock_cov_run:
        mock_pytest_run.return_value = RunOutput(func="test", status=RunState.PASS)
        mock_cov_run.return_value = RunOutput(func="test", status=RunState.PASS)
        res = precheck(params, output)
        assert res.status == RunState.PASS
