# tests/unit/test_file_handler.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for file_handler."""

from pathlib import Path

import pytest

from coding_tools import file_handler


def test_ensure_directory(tmp_path: Path) -> None:
    """Test ensure_directory creates and returns the correct path."""
    target = tmp_path / "nested" / "dir"
    res = file_handler.ensure_directory(target)
    assert res == target
    assert res.is_dir()

    res_str = file_handler.ensure_directory(str(target))
    assert res_str == target
    assert res_str.is_dir()


def test_get_project_root_fallbacks(tmp_path: Path) -> None:
    """Test get_project_root fallback logic when no markers exist."""
    deep_file = tmp_path / "a" / "b" / "file.py"
    deep_file.parent.mkdir(parents=True, exist_ok=True)
    deep_file.write_text("content")

    root = file_handler.get_project_root(deep_file)
    assert root == tmp_path / "a"

    dir_path = tmp_path / "a" / "b"
    root_dir = file_handler.get_project_root(dir_path)
    assert root_dir == dir_path


def test_get_pyproject_and_conftest_paths(tmp_path: Path) -> None:
    """Test get_pyproject_path and get_conftest_path."""
    sub = tmp_path / "src"
    sub.mkdir()
    assert file_handler.get_pyproject_path(sub) == tmp_path / "pyproject.toml"
    assert file_handler.get_conftest_path(sub) == tmp_path / "tests/conftest.py"


def test_get_pytest_log_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_pytest_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    test_path = tmp_path / "tests" / "test_sample.py"
    res = file_handler.get_pytest_log_path(test_path)
    expected = tmp_path / ".pytest_output" / "unit-test-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()

    res_path = file_handler.get_pytest_log_path(
        tmp_path / "tests" / "test_other.py",
    )
    expected_path_correct = (
        tmp_path / ".pytest_output" / "unit-test-test_other.txt"
    )
    assert res_path.resolve() == expected_path_correct.resolve()


def test_get_basedpyright_log_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_basedpyright_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    test_path = tmp_path / "tests" / "test_sample.py"
    res = file_handler.get_basedpyright_log_path(test_path)
    expected = tmp_path / ".pyright_output" / "based-pyright-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_get_ruff_log_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_ruff_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    test_path = tmp_path / "tests" / "test_sample.py"
    res = file_handler.get_ruff_log_path(test_path)
    expected = tmp_path / ".ruff_output" / "ruff-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_get_coverage_annotation_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_coverage_annotation_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    source_path = tmp_path / "src" / "file_handler.py"
    res = file_handler.get_coverage_annotation_path(source_path)
    expected = tmp_path / ".coverage_annotations" / "file_handler.py"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_get_llm_output_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_llm_output_path returns the expected nested path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    params = file_handler.LLMOutputPathParameters(
        llm_name="gemini/flash",
        start_date="26-03-01",
        tool_name="pytest",
        process_step="run",
        target_file=tmp_path / "src" / "main.py",
        status_label="success",
        timestamp=123456789,
        hhmiss="120000",
    )
    res = file_handler.get_llm_output_path(params)
    expected = (
        tmp_path
        / ".llm_output"
        / "gemini-flash"
        / "26-03-01"
        / "120000-pytest-run-main.py-success-123456789.json"
    )
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_all_tool_output_dirs_constant() -> None:
    """Test ALL_TOOL_OUTPUT_DIRS contains all expected directories."""
    dirs = file_handler.ALL_TOOL_OUTPUT_DIRS
    assert isinstance(dirs, set)
    assert file_handler.COVERAGE_ANNOTATIONS_DIR in dirs
    assert file_handler.PYTEST_OUTPUT_DIR in dirs
    assert file_handler.PYRIGHT_OUTPUT_DIR in dirs
    assert file_handler.RUFF_OUTPUT_DIR in dirs
    assert file_handler.LLM_OUTPUT_DIR in dirs
