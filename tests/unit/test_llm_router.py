# tests/unit/test_llm_router.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for llm_router.py."""

from unittest.mock import MagicMock, patch

import pytest

from coding_tools.gemini_client import MODEL_NAME
from coding_tools.llm_router import get_llm_client


@patch("coding_tools.llm_router.GeminiClientAdapter")
def test_get_llm_client_gemini(mock_adapter: MagicMock) -> None:
    """Test getting LLM client for default Gemini model."""
    client = get_llm_client(MODEL_NAME)
    mock_adapter.assert_called_once()
    assert client is mock_adapter.return_value


@patch("coding_tools.llm_router.GeminiClientAdapter")
def test_get_llm_client_lowercase_gemini(mock_adapter: MagicMock) -> None:
    """Test getting LLM client for lowercase Gemini model name."""
    client = get_llm_client("gemini-pro")
    mock_adapter.assert_called_once()
    assert client is mock_adapter.return_value


@patch("coding_tools.llm_router.GeminiClientAdapter")
def test_get_llm_client_model_name_match(mock_adapter: MagicMock) -> None:
    """Test getting LLM client where model_name matches.

    MODEL_NAME when MODEL_NAME doesn't contain gemini.
    """
    with patch("coding_tools.llm_router.MODEL_NAME", "custom-model"):
        client = get_llm_client("custom-model")
        mock_adapter.assert_called_once()
        assert client is mock_adapter.return_value


@pytest.mark.parametrize(
    "unsupported_model",
    [
        "gpt-4",
        "claude-3",
        "llama-3",
    ],
)
def test_get_llm_client_unsupported(unsupported_model: str) -> None:
    """Test getting LLM client with unsupported model raises ValueError."""
    msg = "Unsupported LLM model or provider specified"
    with pytest.raises(ValueError, match=msg):
        get_llm_client(unsupported_model)
