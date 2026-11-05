# tests/unit/test_my_pyright.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the my_pyright module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from coding_tools import my_pyright
from coding_tools.my_run import EditState, RunOutput, RunState


def test_check_edited() -> None:
    """Test check_edited returns KEPT."""
    assert my_pyright.check_edited("out", "err") == EditState.KEPT


@pytest.mark.parametrize(
    ("exit_code", "expected_state"),
    [
        (0, RunState.PASS),
        (1, RunState.FAIL),
    ],
)
def test_check_result(exit_code: int, expected_state: RunState) -> None:
    """Test check_result handles exit codes correctly."""
    run_output = RunOutput(func="old", status=RunState.PRESTART)
    res = my_pyright.check_result("out", "err", exit_code, run_output)
    assert res.status == expected_state
    assert res.sub_func == "coding_tools.my_pyright"
    assert res.edited == EditState.KEPT


def test_clean_log() -> None:
    """Test clean_log removes path patterns."""
    raw = "Some text C:\\path\to\file.py:10:5 and other info"
    cleaned = my_pyright.clean_log(raw)
    assert "file.py" not in cleaned


@patch("coding_tools.my_pyright.my_subprocess.run")
@patch("coding_tools.my_pyright.my_path.get_basedpyright_log_path")
def test_run(
    mock_get_log: MagicMock,
    mock_sub_run: MagicMock,
    tmp_path: Path,
) -> None:
    """Test run invokes subprocess with correct parameters."""
    log_file = tmp_path / "pyright.log"
    mock_get_log.return_value = log_file
    expected_output = RunOutput(func="test", status=RunState.PASS)
    mock_sub_run.return_value = expected_output

    target_file = tmp_path / "test_file.py"
    target_file.write_text("pass", encoding="utf-8")
    initial_output = RunOutput(func="initial", status=RunState.PRESTART)

    res = my_pyright.run(target_file, initial_output)
    assert res == expected_output
    mock_sub_run.assert_called_once()
