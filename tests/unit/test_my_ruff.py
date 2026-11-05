# tests/unit/test_my_ruff.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Test my_ruff module."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from coding_tools.my_ruff import (
    check_edited,
    check_result,
    clean_log,
    no_docstring_files,
    run,
)
from coding_tools.my_run import EditState, RunOutput, RunState


def test_check_edited() -> None:
    """Test check_edited function."""
    assert check_edited("Found 2 errors (2 fixed)", "") == EditState.EDITED
    assert check_edited("No errors found", "") == EditState.KEPT


def test_check_result() -> None:
    """Test check_result function."""
    ro = RunOutput(func="test", status=RunState.PRESTART)
    res_pass = check_result("", "", 0, ro)
    assert res_pass.status == RunState.PASS
    assert res_pass.edited == EditState.KEPT

    res_fail = check_result("Found 1 errors (1 fixed)", "", 1, ro)
    assert res_fail.status == RunState.FAIL
    assert res_fail.edited == EditState.EDITED


def test_clean_log() -> None:
    """Test clean_log function."""
    log = "Warning: some issue\nError: real error"
    cleaned = clean_log(log)
    assert "Warning:" not in cleaned
    assert "Error: real error" in cleaned


@patch("coding_tools.my_subprocess.run")
@patch("coding_tools.my_path.get_ruff_log_path")
def test_run(mock_get_path: MagicMock, mock_sub_run: MagicMock) -> None:
    """Test run function."""
    mock_get_path.return_value = Path("log.txt")
    ro = RunOutput(func="test", status=RunState.PRESTART)
    run("file.py", ro)
    mock_sub_run.assert_called_once()


@patch("subprocess.run")
def test_no_docstring_files(mock_sub: MagicMock) -> None:
    """Test no_docstring_files function."""
    mock_sub.return_value.stdout = (
        "src/file.py:10:1: D100 Missing docstring in public module"
    )
    files = no_docstring_files("src")
    assert Path("src/file.py") in files
