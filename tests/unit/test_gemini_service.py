# tests/unit/test_gemini_client.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Gemini service module."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.genai import errors

import coding_tools.gemini_client as gs


def test_test_generation_response_model() -> None:
    """Test Pydantic model instantiation."""
    resp = gs.TestGenerationResponse(
        message="fixed",
        code="print('hello')",
    )
    assert resp.message == "fixed"
    assert resp.code == "print('hello')"


def test_gemini_spinner() -> None:
    """Test the spinner context manager runs and cleans up."""
    with gs.gemini_spinner("Waiting for Gemini", prefix="TEST"):
        time.sleep(0.1)


def test_load_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test loading a skill file from disk using tmp_path."""
    skills_dir = tmp_path / "config" / "skills"
    skills_dir.mkdir(parents=True)
    skill_file = skills_dir / "unit_test_generation.md"
    skill_file.write_text("# Skill content", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    content = gs.load_skill("unit_test_generation.md")
    assert content == "# Skill content"


def test_upload_static_file() -> None:
    """Test uploading a static reference file."""
    mock_client = MagicMock()
    mock_file = MagicMock()
    mock_client.files.upload.return_value = mock_file

    res = gs.upload_static_file(mock_client, "dummy.txt", "TEST")
    assert res == mock_file
    mock_client.files.upload.assert_called_once()


def test_cleanup_files_success() -> None:
    """Test cleanup of uploaded files successfully."""
    mock_client = MagicMock()
    f1 = MagicMock()
    f1.name = "files/123"
    f2 = None
    f3 = MagicMock()
    f3.name = None  # Should be skipped

    gs.cleanup_files(mock_client, [f1, f2, f3], "TEST")
    mock_client.files.delete.assert_called_once_with(name="files/123")


def test_cleanup_files_api_error() -> None:
    """Test cleanup of files handling APIError gracefully."""
    mock_client = MagicMock()
    f1 = MagicMock()
    f1.name = "files/123"

    api_err = errors.APIError(500, response_json={"error": "Failed"})
    api_err.message = "Failed"
    mock_client.files.delete.side_effect = api_err

    gs.cleanup_files(mock_client, [f1], "TEST")
    mock_client.files.delete.assert_called_once_with(name="files/123")


@pytest.mark.parametrize(
    ("uri_config", "uri_conftest", "uri_source", "expect_exception"),
    [
        ("http://conf", "http://test", "http://src", False),
        (None, "http://test", "http://src", True),
        ("http://conf", None, "http://src", True),
        ("http://conf", "http://test", None, True),
    ],
)
def test_validate_file_uris(
    uri_config: str | None,
    uri_conftest: str | None,
    uri_source: str | None,
    expect_exception: bool,
) -> None:
    """Test validate_file_uris with valid and invalid URIs."""
    fc = MagicMock()
    fc.uri = uri_config
    fct = MagicMock()
    fct.uri = uri_conftest
    fs = MagicMock()
    fs.uri = uri_source

    if expect_exception:
        with pytest.raises(
            ValueError,
            match=r"One or more uploaded file URIs resolved to None.",
        ):
            gs.validate_file_uris(fc, fct, fs)
    else:
        res = gs.validate_file_uris(fc, fct, fs)
        assert res == (uri_config, uri_conftest, uri_source)


def test_generate_coverage_hints_missing_files(tmp_path: Path) -> None:
    """Test generate_coverage_hints when coverage file or source file is missing."""
    assert gs.generate_coverage_hints(str(tmp_path / "nonexistent.py")) == []

    source_path = tmp_path / "source.py"
    cover_path = Path(f"{source_path},cover")
    cover_path.write_text("! line 1", encoding="utf-8")
    assert gs.generate_coverage_hints(str(source_path)) == []


def test_generate_coverage_hints_various_cases(tmp_path: Path) -> None:
    """Test generate_coverage_hints handles conditions, exceptions, and indexes."""
    source_path = tmp_path / "source.py"
    source_lines = [
        "if a and b:",
        "if foo():",
        "except ValueError:",
        "normal line",
    ]
    source_path.write_text("\n".join(source_lines), encoding="utf-8")

    cover_path = Path(f"{source_path},cover")
    cover_lines = [
        "! if a and b:",
        "! if foo():",
        "! except ValueError:",
        "! normal line",
        "! out of bounds index",
    ]
    cover_path.write_text("\n".join(cover_lines), encoding="utf-8")

    hints = gs.generate_coverage_hints(str(source_path))
    assert len(hints) == 3
    assert any("compound boolean" in h for h in hints)
    assert any("conditional block" in h for h in hints)
    assert any("exception handler" in h for h in hints)


@pytest.mark.parametrize("cache_allowed", [True, False])
def test_build_contents_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_allowed: bool,
) -> None:
    """Test building the contents list with cache allowed True and False."""
    monkeypatch.setattr(gs, "CACHE_ALLOWED", cache_allowed)

    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text("[project]", encoding="utf-8")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    conftest = tests_dir / "conftest.py"
    conftest.write_text("# conftest", encoding="utf-8")

    src_file = tmp_path / "dummy_source.py"
    src_file.write_text("if True:\n    pass", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    coverage_content = " line 1\n line 2"
    pytest_output = "PASSED"

    contents = gs.build_contents_list(
        test_file_path="tests/test_foo.py",
        source_file_path=str(src_file),
        test_content="def test_bar(): assert True",
        coverage_content=coverage_content,
        pytest_output=pytest_output,
    )
    assert len(contents) > 0
