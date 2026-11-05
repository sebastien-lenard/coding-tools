# tests/unit/test_llm_protocol.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for llm_protocol.py."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from coding_tools.llm_protocol import (
    LLMAPIError,
    LLMCallParams,
    LLMClientError,
    LLMClientProtocol,
    LLMResponse,
    LLMServerError,
)


class DummyModel(BaseModel):
    """Dummy model for testing structured generation."""

    value: str


class DummyLLMClient:
    """Dummy LLM client implementation for testing the protocol."""

    supports_caching: bool = True

    async def call(
        self,
        req: str,
        params: LLMCallParams,
    ) -> LLMResponse:
        """Generate a dummy structured response."""
        _ = req
        _ = params
        return LLMResponse(message="test", edited_files="test")

    def setup_cache(
        self,
        source_file_path: str,
        prefix: str,
    ) -> tuple[str | None, list[object]]:
        """Set up a dummy cache."""
        _ = source_file_path
        _ = prefix
        return "cache_1", []

    def cleanup_files(self, files: list[object], prefix: str) -> None:
        """Clean up dummy files."""
        _ = files
        _ = prefix


def test_structured_generation_options_defaults() -> None:
    """Test default values for LLMCallParams."""
    options = LLMCallParams(
        response_schema=DummyModel,
        prefix="test_prefix",
    )
    assert options.response_schema == DummyModel
    assert options.prefix == "test_prefix"


def test_llm_client_protocol_implementation() -> None:
    """Test that DummyLLMClient implements LLMClientProtocol correctly."""
    client: LLMClientProtocol = DummyLLMClient()
    res = asyncio.run(
        client.call(
            "req",
            LLMCallParams(response_schema=DummyModel, prefix="p"),
        ),
    )
    assert isinstance(res, LLMResponse)
    assert res.message == "test"


def test_llm_api_error() -> None:
    """Test LLMAPIError initialization and attributes."""
    err = LLMAPIError("api error", status_code=400, error_code="INVALID_ARGUMENT")
    assert str(err) == "api error"
    assert err.status_code == 400
    assert err.error_code == "INVALID_ARGUMENT"


def test_llm_client_error() -> None:
    """Test LLMClientError initialization and attributes."""
    err = LLMClientError("client error", status_code=400, retryable=False)
    assert str(err) == "client error"
    assert err.status_code == 400
    assert err.retryable is False


def test_llm_server_error() -> None:
    """Test LLMServerError initialization and attributes."""
    err = LLMServerError("server error", status_code=503, retryable=True)
    assert str(err) == "server error"
    assert err.status_code == 503
    assert err.retryable is True
