# tests/unit/test_pytest_cov.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Test suite for pytest coverage tools."""

from pathlib import Path
from typing import Never

import pytest

from coding_tools import pytest_cov
from coding_tools.my_run import RunOutput, RunState


def test_pytest_cov_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pytest_cov run when coverage file is missing."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(
        "coding_tools.my_path.pytest_cov_path",
        lambda _: tmp_path / "nonexistent",
    )
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = pytest_cov.run(src, output)
    assert res.status == RunState.FAIL
    assert res.brief == pytest_cov.BRIEF_MISSING


def test_pytest_cov_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pytest_cov run successfully passes."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("pass", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = pytest_cov.run(src, output)
    assert res.status == RunState.PASS


def test_pytest_cov_branch_parsing() -> None:
    """Test branch audit string parsing helper."""
    assert (
        "Partial branch test coverage jump: no branch"
        in pytest_cov._parse_branch_audit("no branch")
    )
    assert "exited early" in pytest_cov._parse_branch_audit("1->exit")
    assert "never taken" in pytest_cov._parse_branch_audit("1->2")
    assert "Partial branch" in pytest_cov._parse_branch_audit("unknown")


def test_pytest_cov_formatting_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling during statement formatting."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("!1", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)

    orig_read_txt = pytest_cov.my_io.read_txt

    def mock_read_txt(path: Path | str, *args: object, **kwargs: object) -> str:
        if "cov_stmt.md" in str(path):
            msg = "Missing template"
            raise RuntimeError(msg)
        return orig_read_txt(path, *args, **kwargs)

    monkeypatch.setattr("coding_tools.my_io.read_txt", mock_read_txt)
    output = RunOutput(func="test", status=RunState.PRESTART)
    with pytest.raises(RuntimeError, match="Missing template"):
        pytest_cov.run(src, output)


def test_pytest_cov_formatting_branch_template_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling during branch template reading."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("pass", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)
    monkeypatch.setattr(
        "coding_tools.my_path.get_pytest_log_path",
        lambda _: tmp_path / "pytest.log",
    )
    log_file = tmp_path / "pytest.log"
    log_file.write_text(f"{src.name} 1->2", encoding="utf-8")

    orig_read_txt = pytest_cov.my_io.read_txt

    def mock_read_txt(path: Path | str, *args: object, **kwargs: object) -> str:
        if "cov_branch.md" in str(path):
            msg = "Missing template"
            raise RuntimeError(msg)
        return orig_read_txt(path, *args, **kwargs)

    monkeypatch.setattr("coding_tools.my_io.read_txt", mock_read_txt)
    output = RunOutput(func="test", status=RunState.PRESTART)
    with pytest.raises(RuntimeError, match="Missing template"):
        pytest_cov.run(src, output)


def test_pytest_cov_src_read_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling when reading source files."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("!1", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)

    orig_read_lines = pytest_cov.my_io.read_lines

    def mock_read_lines(path: Path | str, *args: object, **kwargs: object) -> list[str]:
        if str(path) == str(src):
            msg = "Missing src file"
            raise RuntimeError(msg)
        return orig_read_lines(path, *args, **kwargs)

    monkeypatch.setattr("coding_tools.my_io.read_lines", mock_read_lines)
    output = RunOutput(func="test", status=RunState.PRESTART)
    with pytest.raises(RuntimeError, match="Missing src file"):
        pytest_cov.run(src, output)


def test_pytest_cov_branch_src_read_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling when reading source files for branch analysis."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("pass", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)
    monkeypatch.setattr(
        "coding_tools.my_path.get_pytest_log_path",
        lambda _: tmp_path / "pytest.log",
    )
    log_file = tmp_path / "pytest.log"
    log_file.write_text(f"{src.name} 1->2", encoding="utf-8")

    orig_read_lines = pytest_cov.my_io.read_lines

    def mock_read_lines(path: Path | str, *args: object, **kwargs: object) -> list[str]:
        if str(path) == str(src):
            msg = "Missing src file"
            raise RuntimeError(msg)
        return orig_read_lines(path, *args, **kwargs)

    monkeypatch.setattr("coding_tools.my_io.read_lines", mock_read_lines)
    output = RunOutput(func="test", status=RunState.PRESTART)
    with pytest.raises(RuntimeError, match="Missing src file"):
        pytest_cov.run(src, output)


def test_pytest_cov_stmt_formatting_and_line_overflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test statement formatting and line overflow scenarios."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("!1\n!999", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = pytest_cov.run(src, output)
    assert res.status == RunState.FAIL


def test_pytest_cov_branch_formatting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test branch formatting output checks."""
    src = tmp_path / "dummy.py"
    src.write_text("if True:\n    pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("pass", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)
    monkeypatch.setattr(
        "coding_tools.my_path.get_pytest_log_path",
        lambda _: tmp_path / "pytest.log",
    )
    log_file = tmp_path / "pytest.log"
    log_file.write_text(
        f"{src.name} 1->2, 3->bad\nStmts 1->exit\n999->1000\n1->999",
        encoding="utf-8",
    )
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = pytest_cov.run(src, output)
    assert res.status == RunState.FAIL


def test_pytest_cov_issues_path_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test runtime error handling when fetching coverage path in issues()."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")

    def mock_cov_path(path: Path) -> Never:
        del path
        msg = "Cov path error"
        raise RuntimeError(msg)

    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", mock_cov_path)
    _uncov, _branch, cov_state, run_state = pytest_cov.issues(src)
    assert cov_state == pytest_cov.CovState.MISSING
    assert run_state == pytest_cov.RunState.FAIL


def test_pytest_cov_issues_read_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test runtime error handling during read operation in issues()."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)

    def mock_read(*args: object, **kwargs: object) -> Never:
        del args, kwargs
        msg = "Read error"
        raise RuntimeError(msg)

    monkeypatch.setattr(pytest_cov, "_read", mock_read)
    _uncov, _branch, cov_state, run_state = pytest_cov.issues(src)
    assert cov_state == pytest_cov.CovState.MISSING
    assert run_state == pytest_cov.RunState.FAIL


def test_pytest_uncov_branch_notes_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling in uncov branch notes extraction."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(
        "coding_tools.my_path.get_pytest_log_path",
        lambda _: tmp_path / "nonexistent.log",
    )
    notes = pytest_cov._pytest_uncov_branch_notes(src)
    assert notes == []


def test_pytest_uncov_branch_notes_filtering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test filtering behavior in uncov branch notes extraction."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(
        "coding_tools.my_path.get_pytest_log_path",
        lambda _: tmp_path / "pytest.log",
    )
    log_file = tmp_path / "pytest.log"
    log_file.write_text(
        f"{src.name} 1->2\nUnrelated line\nStmts",
        encoding="utf-8",
    )
    notes = pytest_cov._pytest_uncov_branch_notes(src)
    assert len(notes) == 1


def test_pytest_uncov_branch_notes_raises_and_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test empty return value when branch note log read fails."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(
        "coding_tools.my_path.get_pytest_log_path",
        lambda _: tmp_path / "pytest.log",
    )

    def mock_read_txt(*args: object, **kwargs: object) -> Never:
        del args, kwargs
        msg = "log missing"
        raise FileNotFoundError(msg)

    monkeypatch.setattr(pytest_cov.my_io, "read_txt", mock_read_txt)
    notes = pytest_cov._pytest_uncov_branch_notes(src)
    assert notes == []


def test_fmt_branches_continue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test branch formatting continue statement path."""
    src = tmp_path / "dummy.py"
    src.write_text("pass", encoding="utf-8")
    cov_file = tmp_path / ".pytest_cache" / "cov.txt"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    cov_file.write_text("pass", encoding="utf-8")
    monkeypatch.setattr("coding_tools.my_path.pytest_cov_path", lambda _: cov_file)
    monkeypatch.setattr(
        "coding_tools.my_path.get_pytest_log_path",
        lambda _: tmp_path / "pytest.log",
    )
    log_file = tmp_path / "pytest.log"
    log_file.write_text(f"{src.name} 999->1000", encoding="utf-8")
    output = RunOutput(func="test", status=RunState.PRESTART)
    res = pytest_cov.run(src, output)
    assert res.status == RunState.FAIL
