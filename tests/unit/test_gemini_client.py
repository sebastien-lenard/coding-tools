# tests/unit/test_gemini_client.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for gemini_client module."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from coding_tools.gemini_client import (
    GeminiClientAdapter,
    RetryRequestParameters,
    build_config,
    build_contents_list,
    call_gemini_with_retry,
    gemini_spinner,
    generate_coverage_hints,
    upload_static_file,
    validate_file_uris,
)
from coding_tools.llm_protocol import (
    LLMAPIError,
    LLMServerError,
    StructuredGenerationOptions,
)
from tests.conftest import MockAPIError, MockServerError


class DummyModel(BaseModel):
    """Dummy Pydantic model for testing."""

    message: str
    code: str


def test_gemini_spinner() -> None:
    """Test gemini_spinner context manager runs and outputs dots."""
    with patch("sys.stdout") as mock_stdout:
        with gemini_spinner("Testing", prefix="TEST"):
            time.sleep(1.1)
        assert mock_stdout.write.called


def test_upload_static_file_success(tmp_path: Path) -> None:
    """Test successful static file upload."""
    f = tmp_path / "dummy.txt"
    f.write_text("hello")
    mock_client = MagicMock()
    mock_client.files.upload.return_value = "uploaded_file"

    res = upload_static_file(mock_client, f, "TEST")
    assert res == "uploaded_file"
    mock_client.files.upload.assert_called_once()


@patch("google.genai.errors.APIError", MockAPIError)
def test_upload_static_file_error(tmp_path: Path) -> None:
    """Test file upload handling APIError."""
    f = tmp_path / "dummy.txt"
    f.write_text("hello")
    mock_client = MagicMock()
    api_err = MockAPIError(message="Upload failed", code=400, status="INVALID")
    mock_client.files.upload.side_effect = api_err

    with pytest.raises(LLMAPIError) as exc_info:
        upload_static_file(mock_client, f, "TEST")
    assert "Upload failed" in str(exc_info.value)


@patch("google.genai.errors.APIError", MockAPIError)
def test_upload_static_file_error_no_message(tmp_path: Path) -> None:
    """Test file upload handling APIError with no message attribute."""
    f = tmp_path / "dummy.txt"
    f.write_text("hello")
    mock_client = MagicMock()
    api_err = MockAPIError(message="", code=400, status="INVALID")
    mock_client.files.upload.side_effect = api_err

    with pytest.raises(LLMAPIError) as exc_info:
        upload_static_file(mock_client, f, "TEST")
    assert "Unknown Gemini API error during file upload" in str(exc_info.value)


def test_validate_file_uris_success() -> None:
    """Test validate_file_uris with valid URIs."""
    f1 = MagicMock(uri="uri1")
    f2 = MagicMock(uri="uri2")
    f3 = MagicMock(uri="uri3")
    u1, u2, u3 = validate_file_uris(f1, f2, f3)
    assert (u1, u2, u3) == ("uri1", "uri2", "uri3")


@pytest.mark.parametrize(
    ("f1_uri", "f2_uri", "f3_uri"),
    [
        (None, "uri2", "uri3"),
        ("uri1", None, "uri3"),
        ("uri1", "uri2", None),
    ],
)
def test_validate_file_uris_none(
    f1_uri: str | None, f2_uri: str | None, f3_uri: str | None,
) -> None:
    """Test validate_file_uris raises ValueError if any URI is None."""
    f1 = MagicMock(uri=f1_uri)
    f2 = MagicMock(uri=f2_uri)
    f3 = MagicMock(uri=f3_uri)
    with pytest.raises(
        ValueError, match=r"One or more uploaded file URIs resolved to None.",
    ):
        validate_file_uris(f1, f2, f3)


@pytest.mark.parametrize(
    ("cache_name", "system_instruction", "caching_allowed"),
    [
        ("cache1", None, True),
        (None, "sys_inst", True),
        (None, None, False),
    ],
)
def test_build_config(
    cache_name: str | None, system_instruction: str | None, caching_allowed: bool,
) -> None:
    """Test build_config with various parameters."""
    with patch(
        "coding_tools.gemini_client.is_caching_allowed", return_value=caching_allowed,
    ):
        cfg = build_config(
            DummyModel, system_instruction=system_instruction, cache_name=cache_name,
        )
        assert cfg["response_mime_type"] == "application/json"
        assert cfg["response_schema"] == DummyModel
        if cache_name and caching_allowed:
            assert cfg["cached_content"] == cache_name
        elif system_instruction:
            assert cfg["system_instruction"] == system_instruction


def test_call_gemini_with_retry_success() -> None:
    """Test call_gemini_with_retry successful response."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"message": "hi", "code": "print()"}'
    mock_client.models.generate_content.return_value = mock_resp

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    res = call_gemini_with_retry(params)
    assert res == mock_resp


def test_call_gemini_with_retry_server_error_retryable() -> None:
    """Test call_gemini_with_retry retries on 503 and succeeds."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    err = MockServerError(message="Unavailable", code=503)
    mock_client.models.generate_content.side_effect = [err, mock_resp]

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with (
        patch("time.sleep"),
        patch("coding_tools.gemini_client.ServerError", MockServerError),
    ):
        res = call_gemini_with_retry(params)
    assert res == mock_resp


def test_call_gemini_with_retry_server_error_exhausted() -> None:
    """Test call_gemini_with_retry raises LLMServerError after max retries."""
    mock_client = MagicMock()
    err = MockServerError(message="Unavailable", code=503)
    mock_client.models.generate_content.side_effect = [err, err, err]

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with (
        patch("time.sleep"),
        patch("coding_tools.gemini_client.ServerError", MockServerError),
        pytest.raises(LLMServerError),
    ):
        call_gemini_with_retry(params)


def test_call_gemini_with_retry_server_error_no_message() -> None:
    """Test call_gemini_with_retry raises LLMServerError with default message."""
    mock_client = MagicMock()
    err = MockServerError(message="", code=503)
    mock_client.models.generate_content.side_effect = [err, err, err]

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with (
        patch("time.sleep"),
        patch("coding_tools.gemini_client.ServerError", MockServerError),
    ):
        with pytest.raises(LLMServerError) as exc_info:
            call_gemini_with_retry(params)
        assert "Gemini Server Error persist after retries" in str(exc_info.value)


def test_call_gemini_with_retry_non_503_server_error() -> None:
    """Test call_gemini_with_retry raises LLMServerError immediately."""
    mock_client = MagicMock()
    err = MockServerError(message="Internal Error", code=500)
    mock_client.models.generate_content.side_effect = err

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with (
        patch("coding_tools.gemini_client.ServerError", MockServerError),
        pytest.raises(LLMServerError),
    ):
        call_gemini_with_retry(params)


def test_call_gemini_with_retry_generic_exception() -> None:
    """Test call_gemini_with_retry handles general Exception as LLMAPIError."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("General failure")

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with pytest.raises(LLMAPIError) as exc_info:
        call_gemini_with_retry(params)
    assert "General failure" in str(exc_info.value)


@patch("google.genai.errors.APIError", MockAPIError)
def test_call_gemini_with_retry_api_error() -> None:
    """Test call_gemini_with_retry raises LLMAPIError on general APIError."""
    mock_client = MagicMock()
    err = MockAPIError(message="Bad request", code=400)
    mock_client.models.generate_content.side_effect = err

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with pytest.raises(LLMAPIError):
        call_gemini_with_retry(params)


@patch("google.genai.errors.APIError", MockAPIError)
def test_call_gemini_with_retry_api_error_no_message() -> None:
    """Test call_gemini_with_retry raises LLMAPIError with default message."""
    mock_client = MagicMock()
    err = MockAPIError(message="", code=400)
    mock_client.models.generate_content.side_effect = err

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with pytest.raises(LLMAPIError):
        call_gemini_with_retry(params)


def test_call_gemini_with_retry_none_response() -> None:
    """Test call_gemini_with_retry raises LLMServerError if response is None."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = None

    params = RetryRequestParameters(
        client=mock_client,
        model_name="model",
        contents_list=[],
        config_kwargs={},
        prefix="TEST",
        spinner_msg="waiting",
    )
    with pytest.raises(LLMServerError):
        call_gemini_with_retry(params)


class TestGeminiClientAdapter:
    """Unit tests for GeminiClientAdapter class."""

    @patch("coding_tools.gemini_client.Client")
    def test_init_default(self, mock_client_cls: MagicMock) -> None:
        """Test default initialization."""
        del mock_client_cls
        with patch(
            "coding_tools.gemini_client.get_provider_mapping",
            return_value={"gem5": {}},
        ):
            adapter = GeminiClientAdapter()
            assert adapter.model_name == "gemini-3.5-flash-lite"

    @patch(
        "coding_tools.gemini_client.Client",
        autospec=True,
    )
    def test_init_custom(self, mock_client_cls: MagicMock) -> None:
        """Test custom initialization."""
        del mock_client_cls
        adapter = GeminiClientAdapter(model_name="custom-model")
        assert adapter.model_name == "custom-model"

    @patch("coding_tools.gemini_client.is_caching_allowed", return_value=True)
    @patch("coding_tools.gemini_client.Client")
    def test_supports_caching(
        self, mock_client_cls: MagicMock, mock_cache: MagicMock,
    ) -> None:
        """Test supports_caching property."""
        del mock_client_cls, mock_cache
        adapter = GeminiClientAdapter()
        assert adapter.supports_caching is True

    @patch("coding_tools.gemini_client.persist_llm_output")
    @patch("coding_tools.gemini_client.call_gemini_with_retry")
    @patch("coding_tools.gemini_client.Client")
    def test_generate_structured_response_non_503_server_error(
        self,
        mock_client_cls: MagicMock,
        mock_call: MagicMock,
        mock_persist: MagicMock,
    ) -> None:
        """Test generate_structured_response handles non-503 ServerError."""
        del mock_client_cls, mock_persist
        err = LLMServerError("Server err", status_code=500)
        mock_call.side_effect = err

        adapter = GeminiClientAdapter()
        options = StructuredGenerationOptions(
            response_schema=DummyModel,
            system_instruction="sys",
            cache_name=None,
            prefix="TEST",
            spinner_msg="wait",
        )
        with pytest.raises(LLMServerError):
            adapter.generate_structured_response(["content"], options)

    @patch("coding_tools.gemini_client.persist_llm_output")
    @patch("coding_tools.gemini_client.call_gemini_with_retry")
    @patch("coding_tools.gemini_client.Client")
    def test_generate_structured_response_success(
        self,
        mock_client_cls: MagicMock,
        mock_call: MagicMock,
        mock_persist: MagicMock,
    ) -> None:
        """Test generate_structured_response successful execution."""
        del mock_client_cls, mock_persist
        mock_resp = MagicMock()
        mock_resp.text = '{"message": "hi", "code": "print()"}'
        mock_resp.parsed = DummyModel(message="hi", code="print()")
        mock_call.return_value = mock_resp

        adapter = GeminiClientAdapter()
        options = StructuredGenerationOptions(
            response_schema=DummyModel,
            system_instruction="sys",
            cache_name=None,
            prefix="TEST",
            spinner_msg="wait",
        )
        res = adapter.generate_structured_response(["content"], options)
        assert isinstance(res, DummyModel)
        assert res.message == "hi"

    @patch("coding_tools.gemini_client.persist_llm_output")
    @patch("coding_tools.gemini_client.call_gemini_with_retry")
    @patch("coding_tools.gemini_client.Client")
    def test_generate_structured_response_invalid_json(
        self,
        mock_client_cls: MagicMock,
        mock_call: MagicMock,
        mock_persist: MagicMock,
    ) -> None:
        """Test generate_structured_response handles invalid json."""
        del mock_client_cls, mock_persist
        mock_resp = MagicMock()
        mock_resp.text = "not json"
        mock_resp.parsed = None
        mock_call.return_value = mock_resp

        adapter = GeminiClientAdapter()
        options = StructuredGenerationOptions(
            response_schema=DummyModel,
            system_instruction="sys",
            cache_name=None,
            prefix="TEST",
            spinner_msg="wait",
        )
        with pytest.raises(
            ValueError,
            match=r"GenAI response did not conform to DummyModel schema.",
        ):
            adapter.generate_structured_response(["content"], options)

    @patch("coding_tools.gemini_client.persist_llm_output")
    @patch("coding_tools.gemini_client.call_gemini_with_retry")
    @patch("coding_tools.gemini_client.Client")
    def test_generate_structured_response_server_error(
        self,
        mock_client_cls: MagicMock,
        mock_call: MagicMock,
        mock_persist: MagicMock,
    ) -> None:
        """Test generate_structured_response handles 503 ServerError."""
        del mock_client_cls, mock_persist
        mock_call.side_effect = LLMServerError("Server err", status_code=503)

        adapter = GeminiClientAdapter()
        options = StructuredGenerationOptions(
            response_schema=DummyModel,
            system_instruction="sys",
            cache_name=None,
            prefix="TEST",
            spinner_msg="wait",
        )
        with pytest.raises(LLMServerError):
            adapter.generate_structured_response(["content"], options)

    @patch("coding_tools.gemini_client.persist_llm_output")
    @patch("coding_tools.gemini_client.call_gemini_with_retry")
    @patch(
        "coding_tools.gemini_client.Client",
        autospec=True,
    )
    def test_generate_structured_response_type_error(
        self,
        mock_client_cls: MagicMock,
        mock_call: MagicMock,
        mock_persist: MagicMock,
    ) -> None:
        """Test generate_structured_response handles TypeError."""
        del mock_client_cls, mock_persist
        mock_call.side_effect = TypeError("type err")

        adapter = GeminiClientAdapter()
        options = StructuredGenerationOptions(
            response_schema=DummyModel,
            system_instruction="sys",
            cache_name=None,
            prefix="TEST",
            spinner_msg="wait",
        )
        with pytest.raises(TypeError):
            adapter.generate_structured_response(["content"], options)

    @patch("coding_tools.gemini_client.persist_llm_output")
    @patch(
        "coding_tools.gemini_client.call_gemini_with_retry",
        side_effect=ValueError("val err"),
    )
    @patch("coding_tools.gemini_client.Client")
    def test_generate_structured_response_value_error(
        self,
        mock_client_cls: MagicMock,
        mock_call: MagicMock,
        mock_persist: MagicMock,
    ) -> None:
        """Test generate_structured_response handles ValueError."""
        del mock_client_cls, mock_call, mock_persist
        adapter = GeminiClientAdapter()
        options = StructuredGenerationOptions(
            response_schema=DummyModel,
            system_instruction="sys",
            cache_name=None,
            prefix="TEST",
            spinner_msg="wait",
        )
        with pytest.raises(ValueError, match="val err"):
            adapter.generate_structured_response(["content"], options)

    @patch("coding_tools.gemini_client.persist_llm_output")
    @patch(
        "coding_tools.gemini_client.call_gemini_with_retry",
        side_effect=RuntimeError("runtime err"),
    )
    @patch("coding_tools.gemini_client.Client")
    def test_generate_structured_response_runtime_error(
        self,
        mock_client_cls: MagicMock,
        mock_call: MagicMock,
        mock_persist: MagicMock,
    ) -> None:
        """Test generate_structured_response handles RuntimeError."""
        del mock_client_cls, mock_call, mock_persist
        adapter = GeminiClientAdapter()
        options = StructuredGenerationOptions(
            response_schema=DummyModel,
            system_instruction="sys",
            cache_name=None,
            prefix="TEST",
            spinner_msg="wait",
        )
        with pytest.raises(RuntimeError):
            adapter.generate_structured_response(["content"], options)

    @patch("coding_tools.gemini_client.Client")
    def test_setup_cache_disabled(self, mock_client_cls: MagicMock) -> None:
        """Test setup_cache when caching is disabled."""
        del mock_client_cls
        adapter = GeminiClientAdapter()
        with patch("coding_tools.gemini_client.is_caching_allowed", return_value=False):
            name, files = adapter.setup_cache("source.py", "TEST")
            assert name is None
            assert files == []

    @patch("coding_tools.gemini_client.load_skill", return_value="skill")
    @patch(
        "coding_tools.gemini_client.validate_file_uris",
        return_value=("u1", "u2", "u3"),
    )
    @patch(
        "coding_tools.gemini_client.upload_static_file",
        return_value=MagicMock(uri="u"),
    )
    @patch("coding_tools.gemini_client.Client")
    def test_setup_cache_success(
        self,
        mock_client_cls: MagicMock,
        mock_upload: MagicMock,
        mock_validate: MagicMock,
        mock_skill: MagicMock,
    ) -> None:
        """Test setup_cache successful creation."""
        del mock_upload, mock_validate, mock_skill
        adapter = GeminiClientAdapter()
        with (
            patch("coding_tools.gemini_client.is_caching_allowed", return_value=True),
            patch("coding_tools.gemini_client.get_conftest_path"),
            patch(
                "coding_tools.gemini_client.get_pyproject_path",
                return_value=Path("pyproject.toml"),
            ),
        ):
            mock_cache_obj = MagicMock()
            mock_cache_obj.name = "cache_name"
            mock_client_cls.return_value.caches.create.return_value = mock_cache_obj
            name, files = adapter.setup_cache("source.py", "TEST")
            assert name == "cache_name"
            assert len(files) == 3

    @patch("coding_tools.gemini_client.Client")
    @patch("google.genai.errors.APIError", MockAPIError)
    def test_setup_cache_api_error(
        self,
        mock_client_cls: MagicMock,
    ) -> None:
        """Test setup_cache handling APIError on upload."""
        adapter = GeminiClientAdapter()
        with patch("coding_tools.gemini_client.is_caching_allowed", return_value=True):
            mock_client_cls.return_value.files.upload = MagicMock(
                side_effect=MockAPIError(message="Fail", code=400),
            )
            with pytest.raises(LLMAPIError):
                adapter.setup_cache("source.py", "TEST")

    @patch("coding_tools.gemini_client.load_skill", return_value="skill")
    @patch(
        "coding_tools.gemini_client.validate_file_uris",
        return_value=("u1", "u2", "u3"),
    )
    @patch(
        "coding_tools.gemini_client.upload_static_file",
        return_value=MagicMock(uri="u"),
    )
    @patch("coding_tools.gemini_client.Client")
    def test_setup_cache_create_api_error(
        self,
        mock_client_cls: MagicMock,
        mock_upload: MagicMock,
        mock_validate: MagicMock,
        mock_skill: MagicMock,
    ) -> None:
        """Test setup_cache handling APIError during cache creation."""
        del mock_upload, mock_validate, mock_skill
        adapter = GeminiClientAdapter()
        with (
            patch("coding_tools.gemini_client.is_caching_allowed", return_value=True),
            patch("coding_tools.gemini_client.get_conftest_path"),
            patch(
                "coding_tools.gemini_client.get_pyproject_path",
                return_value=Path("pyproject.toml"),
            ),
        ):
            api_err = MockAPIError(message="Create Fail", code=400)
            mock_client_cls.return_value.caches.create.side_effect = api_err
            with (
                patch("coding_tools.gemini_client.errors.APIError", MockAPIError),
                pytest.raises(LLMAPIError),
            ):
                adapter.setup_cache("source.py", "TEST")

    @patch("coding_tools.gemini_client.load_skill", return_value="skill")
    @patch(
        "coding_tools.gemini_client.validate_file_uris",
        return_value=("u1", "u2", "u3"),
    )
    @patch(
        "coding_tools.gemini_client.upload_static_file",
        return_value=MagicMock(uri="u"),
    )
    @patch("coding_tools.gemini_client.Client")
    def test_setup_cache_create_api_error_no_message(
        self,
        mock_client_cls: MagicMock,
        mock_upload: MagicMock,
        mock_validate: MagicMock,
        mock_skill: MagicMock,
    ) -> None:
        """Test setup_cache handling empty message APIError during creation."""
        del mock_upload, mock_validate, mock_skill
        adapter = GeminiClientAdapter()
        with (
            patch("coding_tools.gemini_client.is_caching_allowed", return_value=True),
            patch("coding_tools.gemini_client.get_conftest_path"),
            patch(
                "coding_tools.gemini_client.get_pyproject_path",
                return_value=Path("pyproject.toml"),
            ),
        ):
            api_err = MockAPIError(message="", code=400)
            mock_client_cls.return_value.caches.create.side_effect = api_err
            with (
                patch("coding_tools.gemini_client.errors.APIError", MockAPIError),
                pytest.raises(LLMAPIError) as exc_info,
            ):
                adapter.setup_cache("source.py", "TEST")
            assert "Unknown Gemini API error during cache creation" in str(
                exc_info.value,
            )

    @patch("coding_tools.gemini_client.Client")
    def test_cleanup_files(self, mock_client_cls: MagicMock) -> None:
        """Test cleanup_files deletes files correctly."""
        adapter = GeminiClientAdapter()
        file_mock = MagicMock()
        file_mock.name = "file_name"
        adapter.cleanup_files([file_mock, None], "TEST")
        mock_client_cls.return_value.files.delete.assert_called_once_with(
            name="file_name",
        )

    @patch("coding_tools.gemini_client.Client")
    def test_cleanup_files_api_error(self, mock_client_cls: MagicMock) -> None:
        """Test cleanup_files handles APIError gracefully."""
        adapter = GeminiClientAdapter()
        file_mock = MagicMock()
        file_mock.name = "file_name"
        api_err = MockAPIError(message="Del Fail", code=400)
        mock_client_cls.return_value.files.delete.side_effect = api_err
        with patch("coding_tools.gemini_client.errors.APIError", MockAPIError):
            adapter.cleanup_files([file_mock], "TEST")
        mock_client_cls.return_value.files.delete.assert_called_once_with(
            name="file_name",
        )


def test_generate_coverage_hints(tmp_path: Path) -> None:
    """Test generate_coverage_hints reads coverage and source files correctly."""
    src = tmp_path / "source.py"
    src.write_text(
        "if a and b:\n    pass\nif c:\n    pass\nexcept Exception:\n    pass\n",
    )
    cov = tmp_path / "source.py,cover"
    cov.write_text("! line1\n> line2\n! line3\n! line4\n!")

    hints = generate_coverage_hints(str(src))
    assert len(hints) >= 2


def test_generate_coverage_hints_missing(tmp_path: Path) -> None:
    """Test generate_coverage_hints returns empty list if cover file missing."""
    src = tmp_path / "source.py"
    src.write_text("pass")
    hints = generate_coverage_hints(str(src))
    assert hints == []

    src.unlink()
    hints2 = generate_coverage_hints(str(src))
    assert hints2 == []


def test_generate_coverage_hints_index_out_of_bound(tmp_path: Path) -> None:
    """Test generate_coverage_hints handles cover line index >= len(source_lines)."""
    src = tmp_path / "source.py"
    src.write_text("pass")
    cov = tmp_path / "source.py,cover"
    cov.write_text("pass\n! extra line")

    hints = generate_coverage_hints(str(src))
    assert isinstance(hints, list)


def test_generate_coverage_hints_missing_source(tmp_path: Path) -> None:
    """Test generate_coverage_hints returns empty list if source file missing."""
    src = tmp_path / "source.py"
    cov = tmp_path / "source.py,cover"
    cov.write_text("! line1")
    hints = generate_coverage_hints(str(src))
    assert hints == []


@patch("coding_tools.gemini_client.extract_pytest_warnings", return_value="warnings")
@patch("coding_tools.gemini_client.extract_pytest_errors", return_value="errors")
@patch("coding_tools.gemini_client.generate_coverage_hints", return_value=["hint1"])
@patch("coding_tools.gemini_client.extract_uncovered_blocks", return_value=["block1"])
def test_build_contents_list_no_caching(
    mock_uncovered: MagicMock,
    mock_hints: MagicMock,
    mock_err: MagicMock,
    mock_warn: MagicMock,
    tmp_path: Path,
) -> None:
    """Test build_contents_list when caching is disabled."""
    del mock_uncovered, mock_hints, mock_err, mock_warn
    p = tmp_path / "pyproject.toml"
    p.write_text("[project]")
    c = tmp_path / "conftest.py"
    c.write_text("#conftest")
    s = tmp_path / "source.py"
    s.write_text("#source")

    with (
        patch("coding_tools.gemini_client.is_caching_allowed", return_value=False),
        patch("coding_tools.gemini_client.get_pyproject_path", return_value=p),
        patch("coding_tools.gemini_client.get_conftest_path", return_value=c),
    ):
        contents = build_contents_list(
            test_file_path=str(tmp_path / "test_source.py"),
            source_file_path=str(s),
            test_content="# test",
            coverage_content="# cov",
            pytest_output="# out",
        )
    assert len(contents) > 0


@patch("coding_tools.gemini_client.extract_pytest_warnings", return_value="")
@patch("coding_tools.gemini_client.extract_pytest_errors", return_value="")
@patch("coding_tools.gemini_client.generate_coverage_hints", return_value=[])
@patch("coding_tools.gemini_client.extract_uncovered_blocks", return_value=[])
def test_build_contents_list_caching_enabled(
    mock_uncovered: MagicMock,
    mock_hints: MagicMock,
    mock_err: MagicMock,
    mock_warn: MagicMock,
    tmp_path: Path,
) -> None:
    """Test build_contents_list when caching is enabled.

    and no uncovered blocks/hints.
    """
    del mock_uncovered, mock_hints, mock_err, mock_warn
    p = tmp_path / "pyproject.toml"
    p.write_text("[project]")
    c = tmp_path / "conftest.py"
    c.write_text("#conftest")

    with (
        patch("coding_tools.gemini_client.is_caching_allowed", return_value=True),
        patch("coding_tools.gemini_client.get_pyproject_path", return_value=p),
        patch("coding_tools.gemini_client.get_conftest_path", return_value=c),
    ):
        contents = build_contents_list(
            test_file_path=str(tmp_path / "test_source.py"),
            source_file_path=str(tmp_path / "source.py"),
            test_content="# test",
            coverage_content="# cov",
            pytest_output="# out",
        )
    assert len(contents) > 0
