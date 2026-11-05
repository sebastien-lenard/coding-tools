# tests/unit/test_my_path.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for my_path."""

import os
from pathlib import Path

import pytest

from coding_tools import my_path


def test_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test files retrieval helper."""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    f1 = src / "a.py"
    f2 = src / "b.txt"
    f1.write_text("print(1)", encoding="utf-8")
    f2.write_text("hello", encoding="utf-8")

    res_py = my_path.files(src, ext=".py")
    assert res_py == [f1.resolve()]

    res_all = my_path.files(src, ext=None)
    assert res_all == sorted([f1.resolve(), f2.resolve()])

    res_file = my_path.files(f1)
    assert res_file == [f1.resolve()]

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    res_empty = my_path.files(empty_dir, ext=".py")
    assert res_empty == []

    with pytest.raises(FileNotFoundError):
        my_path.files(tmp_path / "non_existent")


def test_ensure_directory(tmp_path: Path) -> None:
    """Test ensure_directory creates and returns the correct path."""
    target = tmp_path / "nested" / "dir"
    res = my_path.ensure_directory(target)
    assert res == target
    assert res.is_dir()

    res_str = my_path.ensure_directory(str(target))
    assert res_str == target
    assert res_str.is_dir()


def test_ensure_directory_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ensure_directory raises OSError when mkdir fails."""
    target = tmp_path / "invalid"
    msg = "Disk error"
    err_obj = OSError(msg)

    def mock_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        raise err_obj

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)

    with pytest.raises(OSError, match=msg):
        my_path.ensure_directory(target)


def test_root_dir_fallbacks(tmp_path: Path) -> None:
    """Test root_dir fallback logic when no markers exist."""
    deep_file = tmp_path / "a" / "b" / "file.py"
    deep_file.parent.mkdir(parents=True, exist_ok=True)
    deep_file.write_text("content", encoding="utf-8")

    root = my_path.root_dir(deep_file)
    assert root == tmp_path / "a" / "b"

    dir_path = tmp_path / "a" / "b"
    root_dir = my_path.root_dir(dir_path)
    assert root_dir == dir_path


def test_get_pyproject_and_conftest_paths(tmp_path: Path) -> None:
    """Test get_pyproject_path and conftest_path."""
    sub = tmp_path / "src"
    sub.mkdir()
    assert my_path.get_pyproject_path(sub) == tmp_path / "pyproject.toml"
    assert my_path.conftest_path(sub) == tmp_path / "tests/conftest.py"


def test_get_pytest_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_pytest_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    test_path = tmp_path / "tests" / "test_sample.py"
    res = my_path.get_pytest_log_path(test_path)
    expected = tmp_path / ".pytest_output" / "unit-test-test-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()

    res_path = my_path.get_pytest_log_path(
        tmp_path / "tests" / "test_other.py",
    )
    expected_path_correct = (
        tmp_path / ".pytest_output" / "unit-test-test-test_other.txt"
    )
    assert res_path.resolve() == expected_path_correct.resolve()


def test_get_basedpyright_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_basedpyright_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    test_path = tmp_path / "tests" / "test_sample.py"
    res = my_path.get_basedpyright_log_path(test_path)
    expected = tmp_path / ".pyright_output" / "based-pyright-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_get_ruff_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_ruff_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    test_path = tmp_path / "tests" / "test_sample.py"
    res = my_path.get_ruff_log_path(test_path)
    expected = tmp_path / ".ruff_output" / "ruff-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_pytest_cov_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pytest_cov_path returns expected path.

    Also handles exact matches/glob matches.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    source_path = tmp_path / "src" / "my_path.py"

    with pytest.raises(RuntimeError):
        my_path.pytest_cov_path(source_path)

    cov_dir = tmp_path / ".coverage_annotations"
    cov_dir.mkdir(parents=True, exist_ok=True)
    match_file = cov_dir / "123_my_path.py,cover"
    match_file.write_text("cov", encoding="utf-8")
    res = my_path.pytest_cov_path(source_path)
    assert res is not None
    assert res.resolve() == match_file.resolve()

    match_file.unlink()
    old_match = cov_dir / "123_my_path.py,cover"
    old_match.write_text("old", encoding="utf-8")
    os.utime(old_match, (1000000.0, 1000000.0))

    new_match = cov_dir / "456_my_path.py,cover"
    new_match.write_text("new", encoding="utf-8")
    os.utime(new_match, (2000000.0, 2000000.0))

    res_glob = my_path.pytest_cov_path(source_path)
    assert res_glob is not None
    assert res_glob.resolve() == new_match.resolve()


def test_llm_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test llm_log_path returns the expected nested path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    target_file = tmp_path / "src" / "main.py"
    target_file.write_text("print(1)", encoding="utf-8")
    res = my_path.llm_log_path(
        func="test_func",
        llm="gemini/flash\test:model",
        input_path=target_file,
    )
    assert res.parent.is_dir()

    with pytest.raises(ValueError, match="No target root given"):
        my_path.llm_log_path(
            func="test_func",
            llm="gemini",
            input_path=None,
            root=None,
        )


def test_all_tool_output_dirs_constant() -> None:
    """Test ALL_TOOL_OUTPUT_DIRS contains all expected directories."""
    dirs = my_path.ALL_TOOL_OUTPUT_DIRS
    assert isinstance(dirs, set)
    assert my_path.COVERAGE_ANNOTATIONS_DIR in dirs
    assert my_path.PYTEST_OUTPUT_DIR in dirs
    assert my_path.PYRIGHT_OUTPUT_DIR in dirs
    assert my_path.RUFF_OUTPUT_DIR in dirs
    assert my_path.LLM_LOG_DIR in dirs


def test_is_unit_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test is_unit_test correctly identifies unit test files."""
    monkeypatch.chdir(tmp_path)
    unit_file = Path("tests/unit/test_foo.py")
    unit_file.parent.mkdir(parents=True, exist_ok=True)
    unit_file.write_text("def test_foo(): pass", encoding="utf-8")
    assert my_path.is_unit_test(unit_file) is True

    other_file = Path("tests/integration/test_bar.py")
    other_file.parent.mkdir(parents=True, exist_ok=True)
    assert my_path.is_unit_test(other_file) is False


def test_latest_path_exceptions(tmp_path: Path) -> None:
    """Test latest_path raises FileNotFoundError when paths or files are missing."""
    with pytest.raises(FileNotFoundError):
        my_path.latest_path(tmp_path / "non_existent", "*.txt")

    sub = tmp_path / "empty"
    sub.mkdir()
    with pytest.raises(FileNotFoundError):
        my_path.latest_path(sub, "*.txt")


def test_rel_path(tmp_path: Path) -> None:
    """Test rel_path handles relative path calculations and exceptions."""
    base = tmp_path / "base"
    target = base / "nested" / "file.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("content", encoding="utf-8")

    assert my_path.rel_path(target, base) == Path("nested/file.py")
    assert my_path.rel_path(target, None) == Path("file.py")

    with pytest.raises(ValueError, match="are same"):
        my_path.rel_path(base, base)

    with pytest.raises(ValueError, match="Bad fit"):
        my_path.rel_path(tmp_path / "other", base)


def test_module_path_and_src_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test module_path and src_path mapping functions."""
    monkeypatch.chdir(tmp_path)
    src_dir = tmp_path / "src" / "pkg"
    src_dir.mkdir(parents=True)
    f = src_dir / "foo.py"
    f.write_text("a = 1", encoding="utf-8")

    assert my_path.module_path(f) == "pkg.foo"

    init_f = tmp_path / "src" / "__init__.py"
    init_f.write_text("a = 1", encoding="utf-8")
    assert my_path.module_path(init_f) == tmp_path.name

    invalid_file = tmp_path / "outside.py"
    invalid_file.write_text("a = 1", encoding="utf-8")
    with pytest.raises(ValueError, match="is not in the subpath of"):
        my_path.module_path(invalid_file)

    tests_dir = tmp_path / "tests" / "unit" / "pkg"
    tests_dir.mkdir(parents=True)
    t_file = tests_dir / "test_foo.py"
    t_file.write_text("def test_foo(): pass", encoding="utf-8")

    mapped = my_path.src_path(t_file)
    assert mapped.resolve() == f.resolve()

    with pytest.raises(FileNotFoundError):
        my_path.src_path(tmp_path / "tests" / "unit" / "pkg" / "test_missing.py")


def test_unit_test_path_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test unit_test_path computes expected test file paths."""
    monkeypatch.chdir(tmp_path)
    src_dir = tmp_path / "src" / "pkg"
    src_dir.mkdir(parents=True)
    f = src_dir / "bar.py"
    f.write_text("b = 2", encoding="utf-8")

    res_list = my_path.unit_test_path(f)
    assert len(res_list) == 1
    assert res_list[0].name == "test_bar.py"

    # Test existing non-empty
    res_list2 = my_path.unit_test_path(f)
    assert len(res_list2) == 1

    init_f = tmp_path / "src" / "__init__.py"
    init_f.write_text("pass", encoding="utf-8")
    assert my_path.unit_test_path(init_f) == []

    invalid_path = tmp_path / "outside_src.py"
    invalid_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="is not in the subpath of"):
        my_path.unit_test_path(invalid_path)


def test_clean_string() -> None:
    """Test clean string transformation."""
    assert my_path.clean(" Hello World! ") == "hello-world"


def test_to_path_list() -> None:
    """Test to_path_list conversion behavior."""
    assert my_path.to_path_list(None) == []
    assert my_path.to_path_list(Path("a.py")) == [Path("a.py")]
    assert my_path.to_path_list("a.py") == [Path("a.py")]
    assert my_path.to_path_list(["a.py", "b.py"]) == [
        Path("a.py"),
        Path("b.py"),
    ]
