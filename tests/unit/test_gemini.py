# tests/unit/test_gemini.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for gemini module."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from coding_tools import gemini
from coding_tools.gemini import (
    Gemini,
    RetryParams,
    _rate_limit_throttle,
    clean_old_timestamps,
    llm_call,
    retry_llm_call,
    set_config,
    should_retry,
)
from coding_tools.llm_protocol import (
    LLMAPIError,
    LLMCallParams,
    LLMClientError,
    LLMServerError,
)
from tests.conftest import MockServerError


class DummyModel(BaseModel):
    """Dummy Pydantic model for testing."""

    message: str
    edited_files: str


class MockClientError(Exception):
    """Global mock replacement for ClientError."""

    def __init__(
        self,
        message: str | None = None,
        code: int = 429,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@pytest.mark.parametrize(
    "response_schema",
    [
        DummyModel,
    ],
)
def test_set_config(
    response_schema: type[BaseModel],
) -> None:
    """Test set_config with various parameters."""
    cfg = set_config(response_schema)
    assert cfg["response_mime_type"] == "application/json"
    assert cfg["response_schema"] == response_schema


@patch("coding_tools.gemini.llm_call")
def test_retry_llm_call_success(mock_llm_call: MagicMock) -> None:
    """Test retry_llm_call successful response."""

    async def _run() -> None:
        mock_client = MagicMock()
        mock_resp = DummyModel(message="hi", edited_files="print()")
        mock_llm_call.return_value = mock_resp

        res = await retry_llm_call(
            RetryParams(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            ),
        )
        assert res == mock_resp

    asyncio.run(_run())


@patch("coding_tools.gemini.should_retry", return_value=(True, 0.0))
@patch("coding_tools.gemini.llm_call")
def test_retry_llm_call_server_error_retryable(
    mock_llm_call: MagicMock,
    mock_should_retry: MagicMock,
) -> None:
    """Test retry_llm_call retries on 503 and succeeds."""

    async def _run() -> None:
        mock_client = MagicMock()
        mock_resp = DummyModel(message="hi", edited_files="print()")
        err = LLMServerError(message="Unavailable", status_code=503, retryable=True)
        mock_llm_call.side_effect = [err, mock_resp]

        with (
            patch("asyncio.sleep", return_value=None),
            patch("google.genai.errors.ServerError", MockServerError),
        ):
            res = await retry_llm_call(
                RetryParams(
                    client=mock_client,
                    req="request",
                    model="model",
                    config={},
                    prefix="TEST",
                ),
            )
        assert res == mock_resp

    asyncio.run(_run())


@patch(
    "coding_tools.gemini.should_retry",
    side_effect=[(True, 0.0), (True, 0.0), (False, 0.0)],
)
@patch("coding_tools.gemini.llm_call")
def test_retry_llm_call_server_error_exhausted(
    mock_llm_call: MagicMock,
    mock_should_retry: MagicMock,
) -> None:
    """Test retry_llm_call raises LLMServerError after max retries."""

    async def _run() -> None:
        mock_client = MagicMock()
        err = LLMServerError(message="Unavailable", status_code=503, retryable=True)
        mock_llm_call.side_effect = [err, err, err]

        with (
            patch("asyncio.sleep"),
            patch("google.genai.errors.ServerError", MockServerError),
            pytest.raises(LLMServerError, match="Unavailable"),
        ):
            await retry_llm_call(
                RetryParams(
                    client=mock_client,
                    req="request",
                    model="model",
                    config={},
                    prefix="TEST",
                ),
            )

    asyncio.run(_run())


@patch("coding_tools.gemini.llm_call")
def test_retry_llm_call_non_503_server_error(mock_llm_call: MagicMock) -> None:
    """Test retry_llm_call raises LLMServerError immediately."""

    async def _run() -> None:
        mock_client = MagicMock()
        err = LLMServerError(message="Internal Error", status_code=500, retryable=False)
        mock_llm_call.side_effect = err

        with (
            patch("google.genai.errors.ServerError", MockServerError),
            pytest.raises(LLMServerError, match="Internal Error"),
        ):
            await retry_llm_call(
                RetryParams(
                    client=mock_client,
                    req="request",
                    model="model",
                    config={},
                    prefix="TEST",
                ),
            )

    asyncio.run(_run())


@patch("coding_tools.gemini.llm_call")
def test_retry_llm_call_generic_exception(mock_llm_call: MagicMock) -> None:
    """Test retry_llm_call handles general Exception as LLMAPIError."""

    async def _run() -> None:
        mock_client = MagicMock()
        mock_llm_call.side_effect = Exception("General failure")

        with pytest.raises(Exception, match="General failure") as exc_info:
            await retry_llm_call(
                RetryParams(
                    client=mock_client,
                    req="request",
                    model="model",
                    config={},
                    prefix="TEST",
                ),
            )
        assert "General failure" in str(exc_info.value)

    asyncio.run(_run())


@patch("coding_tools.gemini.logger.run_spin")
def test_llm_call_client_error(mock_logger_run_spin: MagicMock) -> None:
    """Test llm_call handling ClientError (e.g. 429)."""

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockClientError(message="Rate limit", code=429)
        mock_client.models.generate_content.side_effect = err

        with (
            patch("coding_tools.gemini._rate_limit_throttle"),
            patch("google.genai.errors.ClientError", MockClientError),
            pytest.raises(LLMClientError, match="Rate limit") as exc_info,
        ):
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert exc_info.value.status_code == 429

    asyncio.run(_run())


@patch("coding_tools.gemini.logger.run_spin")
def test_llm_call_client_error_non_429(mock_logger_run_spin: MagicMock) -> None:
    """Test llm_call handling ClientError with code other than 429."""

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockClientError(message="Bad Request", code=400)
        mock_client.models.generate_content.side_effect = err

        with (
            patch("coding_tools.gemini._rate_limit_throttle"),
            patch("google.genai.errors.ClientError", MockClientError),
            pytest.raises(LLMClientError, match="Bad Request") as exc_info,
        ):
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert exc_info.value.status_code == 400

    asyncio.run(_run())


def test_rate_limit_throttle_sleep() -> None:
    """Test _rate_limit_throttle triggers sleep when limit reached."""

    async def _run() -> None:

        now = time.time()
        gemini.CALL_TIMESTAMPS.clear()
        for _ in range(gemini.MAX_REQUESTS_PER_MINUTE):
            gemini.CALL_TIMESTAMPS.append(now)

        mock_sleep = AsyncMock()
        await _rate_limit_throttle(time_func=lambda: now, sleep_func=mock_sleep)
        mock_sleep.assert_called_once()

    asyncio.run(_run())


def test_rate_limit_throttle_no_sleep() -> None:
    """Test _rate_limit_throttle without sleep when limit not reached."""

    async def _run() -> None:

        now = time.time()
        gemini.CALL_TIMESTAMPS.clear()
        gemini.CALL_TIMESTAMPS.append(now - 100.0)

        mock_sleep = AsyncMock()
        await _rate_limit_throttle(time_func=lambda: now, sleep_func=mock_sleep)
        mock_sleep.assert_not_called()

    asyncio.run(_run())


@patch("coding_tools.gemini.logger.run_spin")
def test_llm_call_client_error_exhausted_no_message(
    mock_logger_run_spin: MagicMock,
) -> None:
    """Test llm_call handling ClientError without message attribute."""

    async def _run() -> None:
        mock_client = MagicMock()

        class MockClientErrorNoMsgError(Exception):
            code = 429

            def __init__(self) -> None:
                super().__init__("Raw error")

        err = MockClientErrorNoMsgError()
        mock_client.models.generate_content.side_effect = err

        with (
            patch("coding_tools.gemini._rate_limit_throttle"),
            patch("google.genai.errors.ClientError", MockClientErrorNoMsgError),
            pytest.raises(LLMClientError, match="Raw error"),
        ):
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )

    asyncio.run(_run())


class TestGemini:
    """Unit tests for Gemini class."""

    @patch("coding_tools.gemini.genai.Client")
    @pytest.mark.usefixtures("_mock_client_cls")
    def test_init_default(self) -> None:
        """Test default initialization."""
        with patch(
            "coding_tools.conf.get_provider_mapping",
            return_value={"gemini": {}},
        ):
            adapter = Gemini()
            assert adapter.model_name == "gemini-3.5-flash-lite"

    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls")
    def test_init_custom(self) -> None:
        """Test custom initialization."""
        adapter = Gemini(model_name="custom-model")
        assert adapter.model_name == "custom-model"

    @patch("coding_tools.gemini.my_io.save_llm_req_resp")
    @patch("coding_tools.gemini.retry_llm_call")
    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls", "_mock_save")
    def test_generate_structured_response_success(
        self,
        mock_call: MagicMock,
    ) -> None:
        """Test call successful execution."""

        async def _run() -> None:
            mock_resp = DummyModel(message="hi", edited_files="print()")
            mock_call.return_value = mock_resp

            adapter = Gemini()
            options = LLMCallParams(
                response_schema=DummyModel,
                prefix="TEST",
                tool_name="tool",
                target_file="test.py",
            )
            res = await adapter.call("content", options)
            assert isinstance(res, DummyModel)
            assert res.message == "hi"

        asyncio.run(_run())

    @patch("coding_tools.gemini.my_io.save_llm_req_resp")
    @patch("coding_tools.gemini.retry_llm_call")
    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls", "_mock_save")
    def test_generate_structured_response_invalid_json(
        self,
        mock_call: MagicMock,
    ) -> None:
        """Test call handles invalid json / schema."""

        async def _run() -> None:
            mock_call.return_value = None

            adapter = Gemini()
            options = LLMCallParams(
                response_schema=DummyModel,
                prefix="TEST",
                tool_name="tool",
                target_file="test.py",
            )
            with pytest.raises(
                ValueError,
                match=r"GenAI response did not conform to DummyModel schema.",
            ):
                await adapter.call("content", options)

        asyncio.run(_run())

    @patch("coding_tools.gemini.my_io.save_llm_req_resp")
    @patch(
        "coding_tools.gemini.retry_llm_call",
        side_effect=TypeError("type err"),
    )
    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls", "_mock_retry", "_mock_save")
    def test_generate_structured_response_type_error(
        self,
    ) -> None:
        """Test call handles TypeError."""

        async def _run() -> None:
            adapter = Gemini()
            options = LLMCallParams(
                response_schema=DummyModel,
                prefix="TEST",
                tool_name="tool",
                target_file="test.py",
            )
            with pytest.raises(TypeError, match="type err"):
                await adapter.call("content", options)

        asyncio.run(_run())

    @patch("coding_tools.gemini.my_io.save_llm_req_resp")
    @patch(
        "coding_tools.gemini.retry_llm_call",
        side_effect=ValueError("val err"),
    )
    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls", "_mock_retry", "_mock_save")
    def test_generate_structured_response_value_error(
        self,
    ) -> None:
        """Test call handles ValueError."""

        async def _run() -> None:
            adapter = Gemini()
            options = LLMCallParams(
                response_schema=DummyModel,
                prefix="TEST",
                tool_name="tool",
                target_file="test.py",
            )
            with pytest.raises(ValueError, match="val err"):
                await adapter.call("content", options)

        asyncio.run(_run())

    @patch("coding_tools.gemini.my_io.save_llm_req_resp")
    @patch(
        "coding_tools.gemini.retry_llm_call",
        side_effect=RuntimeError("runtime err"),
    )
    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls", "_mock_retry", "_mock_save")
    def test_generate_structured_response_runtime_error(
        self,
    ) -> None:
        """Test call handles RuntimeError."""

        async def _run() -> None:
            adapter = Gemini()
            options = LLMCallParams(
                response_schema=DummyModel,
                prefix="TEST",
                tool_name="tool",
                target_file="test.py",
            )
            with pytest.raises(RuntimeError, match="runtime err"):
                await adapter.call("content", options)

        asyncio.run(_run())

    @patch("coding_tools.gemini.my_io.save_llm_req_resp")
    @patch("coding_tools.gemini.retry_llm_call")
    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls", "_mock_save")
    def test_generate_structured_response_model_validate_error(
        self,
        mock_call: MagicMock,
    ) -> None:
        """Test call handles model_validate failure raising ValueError."""

        async def _run() -> None:
            mock_call.return_value = {"wrong_key": "val"}

            adapter = Gemini()
            options = LLMCallParams(
                response_schema=DummyModel,
                prefix="TEST",
                tool_name="tool",
                target_file="test.py",
            )
            with pytest.raises(
                ValueError,
                match=r"GenAI response did not conform to "
                r"DummyModel schema.",
            ):
                await adapter.call("content", options)

        asyncio.run(_run())

    @patch(
        "coding_tools.conf.get_provider_mapping",
        return_value={"gemini": {}},
    )
    @patch(
        "coding_tools.gemini.genai.Client",
        autospec=True,
    )
    @pytest.mark.usefixtures("_mock_client_cls", "_mock_conf")
    def test_init_default_fixture(
        self,
    ) -> None:
        """Test init default using mock."""
        adapter = Gemini()
        assert adapter.model_name == "gemini-3.5-flash-lite"


def test_clean_old_timestamps() -> None:
    """Test cleanup of timestamps older than window."""
    timestamps = deque([10.0, 50.0, 70.0])
    clean_old_timestamps(timestamps, now=100.0, window=60.0)
    assert list(timestamps) == [50.0, 70.0]


def test_should_retry() -> None:
    """Test should_retry helper logic for all branches."""
    assert should_retry(503, 0)[0] is True
    assert should_retry(503, 2)[0] is False
    assert should_retry(400, 0)[0] is False


###################################################################################


def test_should_sleep_true_branch() -> None:
    """Test _should_sleep returns condition True when timestamps exceed limit."""
    gemini.CALL_TIMESTAMPS.clear()
    now = time.time()
    for _ in range(gemini.MAX_REQUESTS_PER_MINUTE):
        gemini.CALL_TIMESTAMPS.append(now - 1.0)

    with patch("coding_tools.gemini._max_requests_per_minute", return_value=1):
        cond, _sleep_time = gemini._should_sleep(now)
        assert cond is True
        assert _sleep_time > 0.0


def test_should_sleep_false_branch() -> None:
    """Test _should_sleep returns condition False when sleep_time <= 0."""
    gemini.CALL_TIMESTAMPS.clear()
    now = time.time()
    # Add old timestamp so sleep_time will be negative or zero
    gemini.CALL_TIMESTAMPS.append(now - 70.0)

    with patch("coding_tools.gemini._max_requests_per_minute", return_value=1):
        cond, _sleep_time = gemini._should_sleep(now)
        assert cond is False


@patch("coding_tools.gemini.logger.run_spin")
def test_llm_call_server_error_503(mock_logger_run_spin: MagicMock) -> None:
    """Test llm_call raises LLMServerError on 503 ServerError."""

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockServerError(message="Service Unavailable", code=503)
        mock_client.models.generate_content.side_effect = err

        with (
            patch("coding_tools.gemini._rate_limit_throttle"),
            patch("google.genai.errors.ServerError", MockServerError),
            pytest.raises(LLMServerError, match="Service Unavailable") as exc_info,
        ):
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.retryable is True

    asyncio.run(_run())


@patch("coding_tools.gemini.logger.run_spin")
def test_llm_call_server_error_non_503(mock_logger_run_spin: MagicMock) -> None:
    """Test llm_call raises LLMServerError with retryable False when code is not 503."""

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockServerError(message="Internal Error", code=500)
        mock_client.models.generate_content.side_effect = err

        with (
            patch("coding_tools.gemini._rate_limit_throttle"),
            patch("google.genai.errors.ServerError", MockServerError),
            pytest.raises(LLMServerError, match="Internal Error") as exc_info,
        ):
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert exc_info.value.status_code == 500
        assert exc_info.value.retryable is False

    asyncio.run(_run())


@patch("coding_tools.gemini.logger.run_spin")
def test_llm_call_returns_resp_parsed(mock_logger_run_spin: MagicMock) -> None:
    """Test llm_call returns resp.parsed on success."""

    async def _run() -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        expected_parsed = DummyModel(message="ok", edited_files="none")
        mock_resp.parsed = expected_parsed
        mock_client.models.generate_content.return_value = mock_resp

        with patch("coding_tools.gemini._rate_limit_throttle"):
            res = await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert res == expected_parsed

    asyncio.run(_run())


@patch("coding_tools.gemini.llm_call")
def test_retry_llm_call_returns_resp_directly(mock_llm_call: MagicMock) -> None:
    """Test retry_llm_call returns resp on success via else block."""

    async def _run() -> None:
        mock_client = MagicMock()
        mock_resp = DummyModel(message="hi", edited_files="print()")
        mock_llm_call.return_value = mock_resp

        res = await retry_llm_call(
            RetryParams(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            ),
        )
        assert res == mock_resp

    asyncio.run(_run())


@patch("coding_tools.gemini.logger.run_spin")
def test_llm_call_api_error(mock_logger_run_spin: MagicMock) -> None:
    """Test llm_call raises LLMAPIError on APIError or general Exception."""

    async def _run() -> None:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API failure")

        with (
            patch("coding_tools.gemini._rate_limit_throttle"),
            pytest.raises(LLMAPIError, match="API failure") as exc_info,
        ):
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert "API failure" in str(exc_info.value)

    asyncio.run(_run())


def test_max_retries_zero() -> None:
    """Test retry_llm_call when max retries is zero (range is empty)."""

    async def _run() -> None:
        mock_client = MagicMock()
        with patch("coding_tools.gemini._max_retries", return_value=0):
            res = await retry_llm_call(
                RetryParams(
                    client=mock_client,
                    req="request",
                    model="model",
                    config={},
                    prefix="TEST",
                ),
            )
            assert res is None

    asyncio.run(_run())
