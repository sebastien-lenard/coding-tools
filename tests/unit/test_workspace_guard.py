# tests/unit/test_workspace_guard.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for workspace_guard.py."""

from __future__ import annotations

import contextlib
import runpy
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
from pathlib import Path

import pytest

from coding_tools import workspace_guard
from coding_tools.workspace_guard import WorkspaceGuard


@pytest.fixture(autouse=True)
def clean_cover_files() -> Generator[None, None, None]:
    """Clean up workspace_guard coverage annotation file before and after tests.

    NB: Only the target coverage file is deleted, not other coverage files
    """
    cover_file = Path("src/coding_tools/workspace_guard.py,cover")
    with contextlib.suppress(FileNotFoundError, OSError):
        cover_file.unlink()
    yield
    with contextlib.suppress(FileNotFoundError, OSError):
        cover_file.unlink()


class MockResult:
    """Mock result for subprocess.run."""

    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def test_workspace_guard_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test workspace guard execution via runpy."""
    monkeypatch.chdir(tmp_path)
    ws_module = sys.modules.get("coding_tools.workspace_guard")
    assert ws_module is not None
    assert ws_module.__file__ is not None
    target_file_path = str(Path(ws_module.__file__).resolve())
    monkeypatch.setattr(sys, "argv", ["workspace_guard.py", "--help"])
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(target_file_path, run_name="__main__")
    assert exc_info.value.code in (0, None, 2)


def test_collect_test_files(tmp_path: Path) -> None:
    """Test collecting test files."""
    t_file = tmp_path / "test_sample.py"
    t_file.write_text("def test_foo(): pass")

    ignored_dir = tmp_path / ".venv"
    ignored_dir.mkdir()
    ignored_file = ignored_dir / "test_ignored.py"
    ignored_file.write_text("def test_bar(): pass")

    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()
    sub_file = sub_dir / "test_sub.py"
    sub_file.write_text("def test_sub(): pass")

    files = workspace_guard._collect_test_files(tmp_path)
    assert t_file in files
    assert sub_file in files
    assert ignored_file not in files

    files_single = workspace_guard._collect_test_files(t_file)
    assert files_single == [t_file]

    non_existent = tmp_path / "nonexistent"
    assert workspace_guard._collect_test_files(non_existent) == []


def test_check_static_isolation_nonexistent(tmp_path: Path) -> None:
    """Test static isolation check with nonexistent file."""
    guard = WorkspaceGuard(project_path=tmp_path)
    res, errs = guard.check_static_isolation(tmp_path / "nonexistent.py")
    assert res is True
    assert errs == []


def test_check_static_isolation_syntax_error(tmp_path: Path) -> None:
    """Test static isolation check with syntax error."""
    f = tmp_path / "test_syntax.py"
    f.write_text("def test_bad(syntax error")
    guard = WorkspaceGuard(project_path=tmp_path)
    res, errs = guard.check_static_isolation(f)
    assert res is False
    assert any("SyntaxError" in e for e in errs)


@pytest.mark.parametrize(
    "io_snippet",
    [
        "def test_io_write_text():\n    Path('foo').write_text('bar')\n",
        "def test_io_write_bytes():\n    Path('foo').write_bytes(b'bar')\n",
        "def test_io_mkdir():\n    Path('foo').mkdir()\n",
        "def test_io_open():\n    Path('foo').open('w')\n",
    ],
)
def test_check_static_isolation_violations(
    tmp_path: Path,
    io_snippet: str,
) -> None:
    """Test static isolation check violations."""
    f = tmp_path / "test_io.py"
    f.write_text(io_snippet)
    guard = WorkspaceGuard(project_path=tmp_path)
    res, errs = guard.check_static_isolation(f)
    assert res is False
    assert len(errs) > 0


def test_check_static_isolation_passes(tmp_path: Path) -> None:
    """Test static isolation check passes."""
    f = tmp_path / "test_io_safe.py"
    f.write_text(
        "def test_io(tmp_path):\n"
        "    tmp_path.joinpath('foo').write_text('bar')\n"
        "def test_setup_mock(setup_mock_project):\n"
        "    Path('foo').mkdir()\n"
        "def test_no_io():\n"
        "    assert True\n"
        "def helper_non_test():\n"
        "    Path('foo').write_text('bar')\n",
    )
    guard = WorkspaceGuard(project_path=tmp_path)
    res, errs = guard.check_static_isolation(f)
    assert res is True
    assert errs == []


def test_snapshot_and_pollution(tmp_path: Path) -> None:
    """Test snapshot and runtime pollution checks."""
    guard = WorkspaceGuard(project_path=tmp_path)
    baseline = guard.snapshot_workspace()

    (tmp_path / "notes.txt").write_text("report = 1")
    (tmp_path / "report.log").write_text("report = 1")

    is_clean_allowed, violations_allowed = guard.check_runtime_pollution(
        baseline,
    )
    assert is_clean_allowed is True
    assert violations_allowed == []

    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "unit-test-sub.py").write_text("bad = 1")
    (tmp_path / "bad_file2.py").write_text("bad = 1")

    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "ignored_file.py").write_text("ignored = 1")
    (venv_dir / "test_ignored_py.py").write_text("def test_ignored(): pass")

    is_clean, violations = guard.check_runtime_pollution(baseline)
    assert is_clean is False
    assert any("bad_file2.py" in v for v in violations)
    assert any("sub" in v for v in violations)
    assert not any("notes.txt" in v for v in violations)
    assert not any("ignored_file.py" in v for v in violations)
    assert not any("test_ignored_py.py" in v for v in violations)

    is_clean_pass, violations_pass = guard.check_runtime_pollution(
        guard.snapshot_workspace(),
    )
    assert is_clean_pass is True
    assert violations_pass == []


def test_snapshot_workspace_ignored_suffixes(tmp_path: Path) -> None:
    """Test snapshot workspace ignores specific suffixes."""
    guard = WorkspaceGuard(project_path=tmp_path)
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("hello")
    cover_file = tmp_path / "coverage.cover"
    cover_file.write_text("coverage")
    pyc_file = tmp_path / "module.pyc"
    pyc_file.write_bytes(b"bytes")

    snap = guard.snapshot_workspace()
    assert Path("notes.txt") not in snap
    assert Path("coverage.cover") not in snap
    assert Path("module.pyc") not in snap


def test_snapshot_workspace_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test snapshot workspace handles ValueError on relative_to."""
    guard = WorkspaceGuard(project_path=tmp_path)
    (tmp_path / "file.py").write_text("print('hello')")

    def mock_relative_to(self: Path, other: Path) -> Path:
        msg = "not relative"
        raise ValueError(msg)

    monkeypatch.setattr(Path, "relative_to", mock_relative_to)
    snap = guard.snapshot_workspace()
    assert snap == set()


def test_execute_test_and_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test execute_test_and_guard execution and failure handling."""
    guard = WorkspaceGuard(project_path=tmp_path)
    f = tmp_path / "test_dummy.py"
    f.write_text("def test_dummy(): pass")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )
    success, errors = guard.execute_test_and_guard(f)
    assert success is True
    assert errors == []

    class MockFailResult(MockResult):
        returncode = 1

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockFailResult(),
    )
    success, errors = guard.execute_test_and_guard(f)
    assert success is True
    assert len(errors) > 0


def test_execute_test_and_guard_with_pollution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test execute_test_and_guard detects pollution."""
    guard = WorkspaceGuard(project_path=tmp_path)
    f = tmp_path / "test_dummy.py"
    f.write_text("def test_dummy(): pass")

    def mock_run_polluted(*args: object, **kwargs: object) -> MockResult:
        (tmp_path / "polluted.py").write_text("x = 1")
        return MockResult()

    monkeypatch.setattr("subprocess.run", mock_run_polluted)
    success, errors = guard.execute_test_and_guard(f)
    assert success is False
    assert any("pollution" in err.lower() for err in errors)


def test_execute_test_and_guard_with_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test execute_test_and_guard with code coverage options."""
    guard = WorkspaceGuard(project_path=tmp_path)
    f = tmp_path / "test_dummy.py"
    f.write_text("def test_dummy(): pass")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )

    source_in_src = tmp_path / "src" / "coding_tools" / "foo.py"
    success, _errors = guard.execute_test_and_guard(
        f,
        run_coverage=True,
        source_file_path=source_in_src,
    )
    assert success is True

    source_outside = tmp_path / "foo.py"
    success2, _errors2 = guard.execute_test_and_guard(
        f,
        run_coverage=True,
        source_file_path=source_outside,
    )
    assert success2 is True

    success3, _errors3 = guard.execute_test_and_guard(
        f,
        run_coverage=True,
        source_file_path=None,
    )
    assert success3 is True

    success4, _errors4 = guard.execute_test_and_guard(
        f,
        run_coverage=False,
        source_file_path=None,
    )
    assert success4 is True


def test_run_checks_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test running checks and generating summary."""
    guard = WorkspaceGuard(project_path=tmp_path)
    f = tmp_path / "test_dummy.py"
    f.write_text("def test_dummy(tmp_path): pass")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )

    s_passed, s_res = workspace_guard._run_static_checks(guard, [f])
    assert s_passed is True

    r_passed, r_res = workspace_guard._run_runtime_checks(guard, [f])
    assert r_passed is True

    bad_f = tmp_path / "test_bad_static.py"
    bad_f.write_text("def test_bad(): Path('a').write_text('b')\n")
    s_passed_fail, _ = workspace_guard._run_static_checks(guard, [bad_f])
    assert s_passed_fail is False

    class MockFailResult(MockResult):
        returncode = 1

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockFailResult(),
    )
    r_passed_fail, r_res_fail = workspace_guard._run_runtime_checks(guard, [f])
    assert r_passed_fail is True
    assert any(res["status"] == "WARNING" for res in r_res_fail)

    def mock_run_with_pollution(*args: object, **kwargs: object) -> MockResult:
        (tmp_path / "unauthorized_pollution.py").write_text("polluted = 1")
        return MockResult()

    monkeypatch.setattr("subprocess.run", mock_run_with_pollution)
    r_passed_poll, r_res_poll = workspace_guard._run_runtime_checks(guard, [f])
    assert r_passed_poll is False
    assert any(res["status"] == "FAILED" for res in r_res_poll)

    workspace_guard._print_summary_table(s_res + r_res)


def test_main_cli_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main CLI execution success with --all."""
    monkeypatch.chdir(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "test_sample.py"
    f.write_text("def test_sample(tmp_path): pass")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )
    monkeypatch.setattr(sys, "argv", ["workspace_guard.py", "--all"])

    with pytest.raises(SystemExit) as exc_info:
        workspace_guard.main()
    assert exc_info.value.code == 0


def test_main_cli_default_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main CLI execution default action."""
    monkeypatch.chdir(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "test_sample.py"
    f.write_text("def test_sample(tmp_path): pass")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )
    monkeypatch.setattr(sys, "argv", ["workspace_guard.py"])
    with pytest.raises(SystemExit) as exc_info:
        workspace_guard.main()
    assert exc_info.value.code == 0


def test_main_cli_file_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main CLI execution with file target."""
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "test_sample.py"
    f.write_text("def test_sample(tmp_path): pass")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["workspace_guard.py", str(f), "--static"],
    )
    with pytest.raises(SystemExit) as exc_info:
        workspace_guard.main()
    assert exc_info.value.code == 0


def test_main_cli_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main CLI execution with no files found."""
    monkeypatch.chdir(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    monkeypatch.setattr(sys, "argv", ["workspace_guard.py", "tests"])

    with pytest.raises(SystemExit) as exc_info:
        workspace_guard.main()
    assert exc_info.value.code == 1


def test_main_cli_nonexistent_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main CLI execution with nonexistent target."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["workspace_guard.py", "nonexistent_target"],
    )

    with pytest.raises(SystemExit) as exc_info:
        workspace_guard.main()
    assert exc_info.value.code == 1


def test_main_cli_static_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main CLI execution static only flag."""
    monkeypatch.chdir(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "test_sample.py"
    f.write_text("def test_sample(tmp_path): pass")

    monkeypatch.setattr(sys, "argv", ["workspace_guard.py", "--static"])
    with pytest.raises(SystemExit) as exc_info:
        workspace_guard.main()
    assert exc_info.value.code == 0


def test_main_cli_runtime_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main CLI execution runtime only flag."""
    monkeypatch.chdir(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "test_sample.py"
    f.write_text("def test_sample(tmp_path): pass")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(),
    )
    monkeypatch.setattr(sys, "argv", ["workspace_guard.py", "--runtime"])
    with pytest.raises(SystemExit) as exc_info:
        workspace_guard.main()
    assert exc_info.value.code == 0
