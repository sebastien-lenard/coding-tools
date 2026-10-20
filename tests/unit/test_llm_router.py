# tests/unit/test_llm_router.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for llm_router.py."""

from unittest.mock import MagicMock, patch

import pytest

from coding_tools.llm_router import get_llm_client


def test_get_llm_client_success() -> None:
    """Test getting LLM client successfully with mock provider mapping."""
    mock_adapter_class = MagicMock()
    mock_module = MagicMock()
    mock_module.MockAdapter = mock_adapter_class

    with patch("coding_tools.llm_router.get_provider_mapping") as mock_get_providers, \
         patch("coding_tools.llm_router.importlib.import_module") as mock_import_module:

        mock_import_module.return_value = mock_module
        mock_get_providers.return_value = {
            "test_provider": {
                "models": ["model-a", "Model-B"],
                "adapter": "some.module:MockAdapter",
            },
        }

        client = get_llm_client("model-a")
        assert client is mock_adapter_class.return_value
        mock_adapter_class.assert_called_once_with(model_name="model-a")


def test_get_llm_client_lowercase_match() -> None:
    """Test getting LLM client with lowercase matching."""
    mock_adapter_class = MagicMock()
    mock_module = MagicMock()
    mock_module.MockAdapter = mock_adapter_class

    with patch("coding_tools.llm_router.get_provider_mapping") as mock_get_providers, \
         patch("coding_tools.llm_router.importlib.import_module") as mock_import_module:

        mock_import_module.return_value = mock_module
        mock_get_providers.return_value = {
            "test_provider": {
                "models": ["Model-B"],
                "adapter": "some.module:MockAdapter",
            },
        }

        client = get_llm_client("model-b")
        assert client is mock_adapter_class.return_value


def test_get_llm_client_no_adapter_path() -> None:
    """Test provider missing adapter path skips and eventually raises ValueError."""
    with patch("coding_tools.llm_router.get_provider_mapping") as mock_get_providers:
        mock_get_providers.return_value = {
            "test_provider": {
                "models": ["model-a"],
                "adapter": "",
            },
        }

        msg = (
            "Unsupported LLM model specified or model not found in "
            "provider configuration: model-a"
        )
        with pytest.raises(ValueError, match=msg):
            get_llm_client("model-a")


def test_get_llm_client_default_model() -> None:
    """Test getting LLM client using default model when none specified."""
    mock_adapter_class = MagicMock()
    mock_module = MagicMock()
    mock_module.DefaultAdapter = mock_adapter_class

    with patch("coding_tools.llm_router.get_provider_mapping") as mock_get_providers, \
         patch("coding_tools.llm_router.get_default_model") as mock_get_default, \
         patch("coding_tools.llm_router.importlib.import_module") as mock_import_module:

        mock_get_default.return_value = "default-model"
        mock_import_module.return_value = mock_module
        mock_get_providers.return_value = {
            "test_provider": {
                "models": ["default-model"],
                "adapter": "some.module:DefaultAdapter",
            },
        }

        client = get_llm_client(None)
        assert client is mock_adapter_class.return_value
        mock_get_default.assert_called_once()


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
    with patch("coding_tools.llm_router.get_provider_mapping") as mock_get_providers:
        mock_get_providers.return_value = {
            "gemini": {
                "models": ["gemini-1.5-pro"],
                "adapter": "coding_tools.adapters.gemini:GeminiClientAdapter",
            },
        }
        msg = (
            "Unsupported LLM model specified or model not found in "
            f"provider configuration: {unsupported_model}"
        )
        with pytest.raises(ValueError, match=msg):
            get_llm_client(unsupported_model)
