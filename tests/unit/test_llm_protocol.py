# tests/unit/test_llm_protocol.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for llm_protocol.py."""

from __future__ import annotations

from pydantic import BaseModel

from coding_tools.llm_protocol import LLMClientProtocol, StructuredGenerationOptions


class DummyModel(BaseModel):
    """Dummy model for testing structured generation."""

    value: str


class DummyLLMClient:
    """Dummy LLM client implementation for testing the protocol."""

    supports_caching: bool = True

    def generate_structured_response(
        self,
        contents_list: list[object],
        options: StructuredGenerationOptions,
    ) -> BaseModel:
        """Generate a dummy structured response."""
        _ = contents_list
        _ = options
        return DummyModel(value="test")

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
    """Test default values for StructuredGenerationOptions."""
    options = StructuredGenerationOptions(
        response_schema=DummyModel,
        prefix="test_prefix",
        spinner_msg="Loading...",
    )
    assert options.response_schema == DummyModel
    assert options.prefix == "test_prefix"
    assert options.spinner_msg == "Loading..."
    assert options.system_instruction is None
    assert options.cache_name is None


def test_structured_generation_options_full() -> None:
    """Test full configuration for StructuredGenerationOptions."""
    options = StructuredGenerationOptions(
        response_schema=DummyModel,
        prefix="test_prefix",
        spinner_msg="Loading...",
        system_instruction="Be helpful",
        cache_name="my_cache",
    )
    assert options.system_instruction == "Be helpful"
    assert options.cache_name == "my_cache"


def test_llm_client_protocol_implementation() -> None:
    """Test that DummyLLMClient implements LLMClientProtocol correctly."""
    client: LLMClientProtocol = DummyLLMClient()
    res = client.generate_structured_response(
        [],
        StructuredGenerationOptions(DummyModel, "p", "s"),
    )
    assert isinstance(res, DummyModel)
    assert res.value == "test"
    cache_name, files = client.setup_cache("file.txt", "p")
    assert cache_name == "cache_1"
    assert files == []
    client.cleanup_files([], "p")
