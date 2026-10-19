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
    f3 = object()  # Does not have 'name' attribute

    adapter = gs.GeminiClientAdapter()
    adapter.client = mock_client
    adapter.cleanup_files([f1, f2, f3], "TEST")
    mock_client.files.delete.assert_called_once_with(name="files/123")


def test_cleanup_files_api_error() -> None:
    """Test cleanup of files handling APIError gracefully."""
    mock_client = MagicMock()
    f1 = MagicMock()
    f1.name = "files/123"

    api_err = errors.APIError(500, response_json={"error": "Failed"})
    api_err.message = "Failed"
    mock_client.files.delete.side_effect = api_err

    adapter = gs.GeminiClientAdapter()
    adapter.client = mock_client
    adapter.cleanup_files([f1], "TEST")
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


@pytest.mark.parametrize(
    ("cache_allowed_val", "cache_name", "sys_instruction", "expected_keys"),
    [
        (True, "my-cache", None, ["cached_content"]),
        (False, None, "instruct", ["system_instruction"]),
        (False, None, None, []),
    ],
)
def test_build_config(
    monkeypatch: pytest.MonkeyPatch,
    cache_allowed_val: bool,
    cache_name: str | None,
    sys_instruction: str | None,
    expected_keys: list[str],
) -> None:
    """Test build_config with various cache and system instruction combinations."""
    monkeypatch.setattr(gs, "CACHE_ALLOWED", cache_allowed_val)
    config = gs.build_config(
        response_schema=gs.TestGenerationResponse,
        system_instruction=sys_instruction,
        cache_name=cache_name,
    )
    for key in expected_keys:
        assert key in config
    if not expected_keys:
        assert "cached_content" not in config
        assert "system_instruction" not in config


def test_call_gemini_with_retry_success() -> None:
    """Test successful call to Gemini without retries."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    res = gs.call_gemini_with_retry(
        client=mock_client,
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="Waiting",
    )
    assert res == mock_response


def test_call_gemini_with_retry_503_retry_then_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 503 error triggering retry then success."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    mock_client = MagicMock()
    mock_response = MagicMock()
    err_503 = errors.ServerError(503, response_json={"error": "Unavailable"})
    err_503.code = 503
    mock_client.models.generate_content.side_effect = [err_503, mock_response]

    res = gs.call_gemini_with_retry(
        client=mock_client,
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="Waiting",
    )
    assert res == mock_response


def test_call_gemini_with_retry_503_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 503 error persisting through max retries."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    mock_client = MagicMock()
    err_503 = errors.ServerError(503, response_json={"error": "Unavailable"})
    err_503.code = 503
    mock_client.models.generate_content.side_effect = [err_503, err_503, err_503]

    with pytest.raises(errors.ServerError):
        gs.call_gemini_with_retry(
            client=mock_client,
            contents_list=[],
            config_kwargs={},
            prefix="TEST",
            spinner_msg="Waiting",
        )


def test_call_gemini_with_retry_other_server_error() -> None:
    """Test non-503 ServerError raising immediately."""
    mock_client = MagicMock()
    err_500 = errors.ServerError(500, response_json={"error": "Error"})
    err_500.code = 500
    mock_client.models.generate_content.side_effect = err_500

    with pytest.raises(errors.ServerError):
        gs.call_gemini_with_retry(
            client=mock_client,
            contents_list=[],
            config_kwargs={},
            prefix="TEST",
            spinner_msg="Waiting",
        )


def test_call_gemini_with_retry_response_none() -> None:
    """Test RuntimeError when response is None after retries."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = None
    with pytest.raises(
        RuntimeError,
        match="Failed to generate content after max retries",
    ):
        gs.call_gemini_with_retry(
            client=mock_client,
            contents_list=[],
            config_kwargs={},
            prefix="TEST",
            spinner_msg="Waiting",
        )


def test_generate_structured_response_parsed_none() -> None:
    """Test ValueError when response.parsed is None."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = None
    mock_client.models.generate_content.return_value = mock_response

    adapter = gs.GeminiClientAdapter()
    adapter.client = mock_client

    options = MagicMock()
    options.response_schema = gs.TestGenerationResponse
    options.system_instruction = None
    options.cache_name = None
    options.prefix = "TEST"
    options.spinner_msg = "Waiting"

    with pytest.raises(ValueError, match="GenAI response did not conform"):
        adapter.generate_structured_response([], options)


def test_generate_structured_response_success() -> None:
    """Test successful structured request execution."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = {"message": "ok", "code": "pass"}
    mock_client.models.generate_content.return_value = mock_response

    adapter = gs.GeminiClientAdapter()
    adapter.client = mock_client

    options = MagicMock()
    options.response_schema = gs.TestGenerationResponse
    options.system_instruction = None
    options.cache_name = None
    options.prefix = "TEST"
    options.spinner_msg = "Waiting"

    res = adapter.generate_structured_response([], options)
    assert isinstance(res, gs.TestGenerationResponse)
    assert res.message == "ok"


def test_create_text_part() -> None:
    """Test create_text_part helper."""
    part = gs.create_text_part("test text")
    assert part is not None


def test_setup_cache_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test setup_cache when CACHE_ALLOWED is True."""
    monkeypatch.setattr(gs, "CACHE_ALLOWED", True)
    monkeypatch.chdir(tmp_path)

    skills_dir = tmp_path / "config" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "unit_test_generation.md").write_text("skill", encoding="utf-8")

    (tmp_path / "project.toml").write_text("[project]", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_text("conftest", encoding="utf-8")
    src = tmp_path / "src.py"
    src.write_text("src", encoding="utf-8")

    mock_client = MagicMock()
    f1 = MagicMock()
    f1.uri = "uri_conf"
    f2 = MagicMock()
    f2.uri = "uri_conftest"
    f3 = MagicMock()
    f3.uri = "uri_source"
    mock_client.files.upload.side_effect = [f1, f2, f3]

    mock_cache = MagicMock()
    mock_cache.name = "cache/123"
    mock_client.caches.create.return_value = mock_cache

    adapter = gs.GeminiClientAdapter()
    adapter.client = mock_client

    cache_name, uploaded = adapter.setup_cache(str(src), "TEST")
    assert cache_name == "cache/123"
    assert len(uploaded) == 3


def test_setup_cache_disabled() -> None:
    """Test setup_cache when CACHE_ALLOWED is False."""
    adapter = gs.GeminiClientAdapter()
    cache_name, uploaded = adapter.setup_cache("dummy.py", "TEST")
    assert cache_name is None
    assert uploaded == []


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
