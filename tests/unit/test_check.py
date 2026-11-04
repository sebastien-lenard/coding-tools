# tests/unit/test_check.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for coding_tools check module."""

from pathlib import Path

from coding_tools.check import CheckParams, default_check_func
from coding_tools.my_run import RunOutput, RunState


def test_default_check_func(tmp_path: Path) -> None:
    """Test the default check function behavior."""
    params = CheckParams(old_txt="old", new_txt="new", file_path=tmp_path / "file.txt")
    output = RunOutput(func="dummy", status=RunState.FAIL)
    result = default_check_func(params, output)
    assert result.status == RunState.SKIP
    assert result.sub_func == "check"
