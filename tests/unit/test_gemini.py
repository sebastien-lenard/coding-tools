# tests/unit/test_gemini.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for gemini module."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock

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


def test_retry_llm_call_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retry_llm_call successful response."""
    mock_resp = DummyModel(message="hi", edited_files="print()")
    mock_llm_call = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr("coding_tools.gemini.llm_call", mock_llm_call)

    async def _run() -> None:
        mock_client = MagicMock()

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


def test_retry_llm_call_server_error_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retry_llm_call retries on 503 and succeeds."""
    mock_resp = DummyModel(message="hi", edited_files="print()")
    err = LLMServerError(message="Unavailable", status_code=503, retryable=True)

    mock_llm_call = AsyncMock(side_effect=[err, mock_resp])
    monkeypatch.setattr("coding_tools.gemini.llm_call", mock_llm_call)
    monkeypatch.setattr(
        "coding_tools.gemini.should_retry",
        lambda *args, **kwargs: (True, 0.0),
    )

    async def _run() -> None:
        mock_client = MagicMock()

        monkeypatch.setattr("asyncio.sleep", lambda *args, **kwargs: None)
        monkeypatch.setattr("google.genai.errors.ServerError", MockServerError)

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


def test_retry_llm_call_server_error_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retry_llm_call raises LLMServerError after max retries."""
    mock_llm_call = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.llm_call", mock_llm_call)
    side_effects = iter([(True, 0.0), (True, 0.0), (False, 0.0)])
    monkeypatch.setattr(
        "coding_tools.gemini.should_retry",
        lambda *args, **kwargs: next(side_effects),
    )

    async def _run() -> None:
        mock_client = MagicMock()
        err = LLMServerError(message="Unavailable", status_code=503, retryable=True)
        mock_llm_call.side_effect = [err, err, err]

        monkeypatch.setattr("asyncio.sleep", lambda *args, **kwargs: None)
        monkeypatch.setattr("google.genai.errors.ServerError", MockServerError)

        with pytest.raises(LLMServerError, match="Unavailable"):
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


def test_retry_llm_call_non_503_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retry_llm_call raises LLMServerError immediately."""
    mock_llm_call = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.llm_call", mock_llm_call)

    async def _run() -> None:
        mock_client = MagicMock()
        err = LLMServerError(message="Internal Error", status_code=500, retryable=False)
        mock_llm_call.side_effect = err

        monkeypatch.setattr("google.genai.errors.ServerError", MockServerError)

        with pytest.raises(LLMServerError, match="Internal Error"):
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


def test_retry_llm_call_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retry_llm_call handles general Exception as LLMAPIError."""
    mock_llm_call = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.llm_call", mock_llm_call)

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


def test_llm_call_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test llm_call handling ClientError (e.g. 429)."""
    mock_logger_run_spin = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.logger.run_spin", mock_logger_run_spin)

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockClientError(message="Rate limit", code=429)
        mock_client.models.generate_content.side_effect = err

        monkeypatch.setattr("coding_tools.gemini._rate_limit_throttle", AsyncMock())
        monkeypatch.setattr("google.genai.errors.ClientError", MockClientError)

        with pytest.raises(LLMClientError, match="Rate limit") as exc_info:
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert exc_info.value.status_code == 429

    asyncio.run(_run())


def test_llm_call_client_error_non_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test llm_call handling ClientError with code other than 429."""
    mock_logger_run_spin = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.logger.run_spin", mock_logger_run_spin)

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockClientError(message="Bad Request", code=400)
        mock_client.models.generate_content.side_effect = err

        monkeypatch.setattr("coding_tools.gemini._rate_limit_throttle", AsyncMock())
        monkeypatch.setattr("google.genai.errors.ClientError", MockClientError)

        with pytest.raises(LLMClientError, match="Bad Request") as exc_info:
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


def test_llm_call_client_error_exhausted_no_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test llm_call handling ClientError without message attribute."""
    mock_logger_run_spin = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.logger.run_spin", mock_logger_run_spin)

    async def _run() -> None:
        mock_client = MagicMock()

        class MockClientErrorNoMsgError(Exception):
            code = 429

            def __init__(self) -> None:
                super().__init__("Raw error")

        err = MockClientErrorNoMsgError()
        mock_client.models.generate_content.side_effect = err

        monkeypatch.setattr("coding_tools.gemini._rate_limit_throttle", AsyncMock())
        monkeypatch.setattr(
            "google.genai.errors.ClientError",
            MockClientErrorNoMsgError,
        )

        with pytest.raises(LLMClientError, match="Raw error"):
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

    def test_init_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default initialization."""
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())
        monkeypatch.setattr(
            "coding_tools.conf.get_provider_mapping",
            lambda: {"gemini": {}},
        )
        adapter = Gemini()
        assert adapter.model_name == "gemini-3.5-flash-lite"

    def test_init_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test custom initialization."""
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())
        adapter = Gemini(model_name="custom-model")
        assert adapter.model_name == "custom-model"

    def test_generate_structured_response_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test call successful execution."""
        mock_resp = DummyModel(message="hi", edited_files="print()")
        mock_call = AsyncMock(return_value=mock_resp)
        monkeypatch.setattr("coding_tools.gemini.retry_llm_call", mock_call)
        monkeypatch.setattr("coding_tools.gemini.my_io.save_llm_req_resp", MagicMock())
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())

        async def _run() -> None:
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

    def test_generate_structured_response_invalid_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test call handles invalid json / schema."""
        # Use AsyncMock with return_value=None
        mock_call = AsyncMock(return_value=None)
        monkeypatch.setattr("coding_tools.gemini.retry_llm_call", mock_call)
        monkeypatch.setattr("coding_tools.gemini.my_io.save_llm_req_resp", MagicMock())
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())

        async def _run() -> None:
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

    def test_generate_structured_response_type_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test call handles TypeError."""
        monkeypatch.setattr(
            "coding_tools.gemini.retry_llm_call",
            AsyncMock(side_effect=TypeError("type err")),
        )
        monkeypatch.setattr("coding_tools.gemini.my_io.save_llm_req_resp", MagicMock())
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())

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

    def test_generate_structured_response_value_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test call handles ValueError."""
        monkeypatch.setattr(
            "coding_tools.gemini.retry_llm_call",
            AsyncMock(side_effect=ValueError("val err")),
        )
        monkeypatch.setattr("coding_tools.gemini.my_io.save_llm_req_resp", MagicMock())
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())

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

    def test_generate_structured_response_runtime_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test call handles RuntimeError."""
        monkeypatch.setattr(
            "coding_tools.gemini.retry_llm_call",
            AsyncMock(side_effect=RuntimeError("runtime err")),
        )
        monkeypatch.setattr("coding_tools.gemini.my_io.save_llm_req_resp", MagicMock())
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())

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

    def test_generate_structured_response_model_validate_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test call handles model_validate failure raising ValueError."""
        mock_call = AsyncMock(return_value={"wrong_key": "val"})
        monkeypatch.setattr("coding_tools.gemini.retry_llm_call", mock_call)
        monkeypatch.setattr("coding_tools.gemini.my_io.save_llm_req_resp", MagicMock())
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())

        async def _run() -> None:
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

    def test_init_default_fixture(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test init default using mock."""
        monkeypatch.setattr("coding_tools.gemini.genai.Client", MagicMock())
        monkeypatch.setattr(
            "coding_tools.conf.get_provider_mapping",
            lambda: {"gemini": {}},
        )
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


def test_should_sleep_true_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _should_sleep returns condition True when timestamps exceed limit."""
    gemini.CALL_TIMESTAMPS.clear()
    now = time.time()
    for _ in range(gemini.MAX_REQUESTS_PER_MINUTE):
        gemini.CALL_TIMESTAMPS.append(now - 1.0)

    monkeypatch.setattr("coding_tools.gemini._max_requests_per_minute", lambda: 1)
    cond, _sleep_time = gemini._should_sleep(now)
    assert cond is True
    assert _sleep_time > 0.0


def test_should_sleep_false_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _should_sleep returns condition False when sleep_time <= 0."""
    gemini.CALL_TIMESTAMPS.clear()
    now = time.time()
    gemini.CALL_TIMESTAMPS.append(now - 70.0)

    monkeypatch.setattr("coding_tools.gemini._max_requests_per_minute", lambda: 1)
    cond, _sleep_time = gemini._should_sleep(now)
    assert cond is False


def test_llm_call_server_error_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test llm_call raises LLMServerError on 503 ServerError."""
    mock_logger_run_spin = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.logger.run_spin", mock_logger_run_spin)

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockServerError(message="Service Unavailable", code=503)
        mock_client.models.generate_content.side_effect = err

        monkeypatch.setattr("coding_tools.gemini._rate_limit_throttle", AsyncMock())
        monkeypatch.setattr("google.genai.errors.ServerError", MockServerError)

        with pytest.raises(LLMServerError, match="Service Unavailable") as exc_info:
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


def test_llm_call_server_error_non_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test llm_call raises LLMServerError with retryable False when code is not 503."""
    mock_logger_run_spin = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.logger.run_spin", mock_logger_run_spin)

    async def _run() -> None:
        mock_client = MagicMock()
        err = MockServerError(message="Internal Error", code=500)
        mock_client.models.generate_content.side_effect = err

        monkeypatch.setattr("coding_tools.gemini._rate_limit_throttle", AsyncMock())
        monkeypatch.setattr("google.genai.errors.ServerError", MockServerError)

        with pytest.raises(LLMServerError, match="Internal Error") as exc_info:
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


def test_llm_call_returns_resp_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test llm_call returns resp.parsed on success."""
    mock_logger_run_spin = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.logger.run_spin", mock_logger_run_spin)

    async def _run() -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        expected_parsed = DummyModel(message="ok", edited_files="none")
        mock_resp.parsed = expected_parsed
        mock_client.models.generate_content.return_value = mock_resp

        monkeypatch.setattr("coding_tools.gemini._rate_limit_throttle", AsyncMock())
        res = await llm_call(
            client=mock_client,
            req="request",
            model="model",
            config={},
            prefix="TEST",
        )
        assert res == expected_parsed

    asyncio.run(_run())


def test_retry_llm_call_returns_resp_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retry_llm_call returns resp on success via else block."""
    mock_resp = DummyModel(message="hi", edited_files="print()")
    # Use AsyncMock or async function so it can be awaited by retry_llm_call
    mock_llm_call = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr("coding_tools.gemini.llm_call", mock_llm_call)

    async def _run() -> None:
        mock_client = MagicMock()

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


def test_llm_call_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test llm_call raises LLMAPIError on APIError or general Exception."""
    mock_logger_run_spin = MagicMock()
    monkeypatch.setattr("coding_tools.gemini.logger.run_spin", mock_logger_run_spin)

    async def _run() -> None:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API failure")

        monkeypatch.setattr("coding_tools.gemini._rate_limit_throttle", AsyncMock())

        with pytest.raises(LLMAPIError, match="API failure") as exc_info:
            await llm_call(
                client=mock_client,
                req="request",
                model="model",
                config={},
                prefix="TEST",
            )
        assert "API failure" in str(exc_info.value)

    asyncio.run(_run())


def test_max_retries_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retry_llm_call when max retries is zero (range is empty)."""

    async def _run() -> None:
        mock_client = MagicMock()
        monkeypatch.setattr("coding_tools.gemini._max_retries", lambda: 0)
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
