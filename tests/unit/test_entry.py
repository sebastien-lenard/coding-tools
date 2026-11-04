# tests/unit/test_entry.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for entry module."""

import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from coding_tools import entry


def test_pen_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pen_header entry point."""
    called: list[bool] = []
    monkeypatch.setattr(entry.lead, "main", lambda: called.append(True))
    monkeypatch.setattr("sys.argv", ["prog"])
    entry.pen_header()
    assert called == [True]
    assert "pen-header" in entry.sys.argv


def test_pen_docstring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pen_docstring entry point."""
    called: list[bool] = []
    monkeypatch.setattr(entry.lead, "main", lambda: called.append(True))
    monkeypatch.setattr("sys.argv", ["prog"])
    entry.pen_docstring()
    assert called == [True]
    assert "pen-docstring" in entry.sys.argv


def test_fix_lint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fix_lint entry point."""
    called: list[bool] = []
    monkeypatch.setattr(entry.lead, "main", lambda: called.append(True))
    monkeypatch.setattr("sys.argv", ["prog"])
    entry.fix_lint()
    assert called == [True]
    assert "fix-lint" in entry.sys.argv


def test_fix_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fix_type entry point."""
    called: list[bool] = []
    monkeypatch.setattr(entry.lead, "main", lambda: called.append(True))
    monkeypatch.setattr("sys.argv", ["prog"])
    entry.fix_type()
    assert called == [True]
    assert "fix-type" in entry.sys.argv


def test_pen_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pen_test entry point."""
    called: list[bool] = []
    monkeypatch.setattr(entry.lead, "main", lambda: called.append(True))
    monkeypatch.setattr("sys.argv", ["prog"])
    entry.pen_test()
    assert called == [True]
    assert "pen-test" in entry.sys.argv
    assert "--test" in entry.sys.argv


def test_entry_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test entry main execution via runpy."""
    target_file = str(Path(entry.__file__).resolve())
    monkeypatch.chdir(tmp_path)
    with patch("coding_tools.lead.main"):
        runpy.run_path(target_file, run_name="__main__")
    assert True
