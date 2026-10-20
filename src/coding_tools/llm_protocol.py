# src/coding_tools/llm_protocol.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Provider-agnostic protocol and shared models for LLM client wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class TestGenerationResponse(BaseModel):
    """Define the expected JSON structure returned by code-generation LLMs."""

    message: str
    code: str


@dataclass
class StructuredGenerationOptions:
    """Encapsulates parameters for structured text generation."""

    response_schema: type[BaseModel]
    prefix: str
    spinner_msg: str
    system_instruction: str | None = None
    cache_name: str | None = None


class LLMClientProtocol(Protocol):  # pragma: no cover
    """Defines high-level operations required from any LLM client."""

    @property
    def supports_caching(self) -> bool:
        """Return whether this client adapter supports remote caching."""
        ...

    def generate_structured_response(
        self,
        contents_list: list[object],
        options: StructuredGenerationOptions,
    ) -> BaseModel:
        """Generate a validated Pydantic model response from contents."""
        ...

    def setup_cache(
        self,
        source_file_path: str,
        prefix: str,
    ) -> tuple[str | None, list[object]]:
        """Set up optional file caching and return cache name and uploaded files."""
        ...

    def cleanup_files(self, files: list[object], prefix: str) -> None:
        """Clean up remote uploaded static files safely."""
        ...
