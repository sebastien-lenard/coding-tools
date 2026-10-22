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


def test_get_pytest_log_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_pytest_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    test_path = "tests/unit/test_sample.py"
    res = file_handler.get_pytest_log_path(test_path)
    expected = tmp_path / ".pytest_output" / "unit-test-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()

    res_path = file_handler.get_pytest_log_path(
        Path("tests/unit/test_other.py"),
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
    test_path = Path("tests/unit/test_sample.py")
    res = file_handler.get_basedpyright_log_path(test_path)
    expected = tmp_path / ".pyright_output" / "based-pyright-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_get_ruff_log_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_ruff_log_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    test_path = "tests/unit/test_sample.py"
    res = file_handler.get_ruff_log_path(test_path)
    expected = tmp_path / ".ruff_output" / "ruff-test_sample.txt"
    assert res.resolve() == expected.resolve()
    assert expected.parent.is_dir()


def test_get_coverage_annotation_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test get_coverage_annotation_path returns the expected path."""
    monkeypatch.chdir(tmp_path)
    source_path = "src/coding_tools/file_handler.py"
    res = file_handler.get_coverage_annotation_path(source_path)
    expected = tmp_path / ".coverage_annotations" / "file_handler.py,cover"
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
