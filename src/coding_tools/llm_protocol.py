# src/coding_tools/llm_protocol.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Give protocol, shared models, and exceptions for LLM wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base exception for LLM errors."""


class LLMAPIError(LLMError):
    """Agnostic API error mirroring provider failure details."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class LLMServerError(LLMError):
    """Agnostic server error mirroring server failure and retries."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class LLMResponse(BaseModel):
    """Expected JSON structure for LLMs."""

    message: str
    code: str


@dataclass
class StructuredGenerationOptions:
    """Params for structured text writing."""

    response_schema: type[BaseModel]
    prefix: str
    spinner_msg: str
    system_instruction: str | None = None
    cache_name: str | None = None
    tool_name: str = "generic-tool"
    process_step: str = "generation"
    target_file: str = "unknown.py"
    start_date: str = "26-01-01"
    llm_name: str = "generic-model"


class LLMClientProtocol(Protocol):
    """High-level ops for any LLM client."""

    @property
    def supports_caching(self) -> bool:
        """Check if client supports remote caching."""
        ...

    def generate_structured_response(
        self,
        contents_list: list[object],
        options: StructuredGenerationOptions,
    ) -> BaseModel:
        """Get checked Pydantic model response from contents."""
        ...

    def setup_cache(
        self,
        source_file_path: str,
        prefix: str,
    ) -> tuple[str | None, list[object]]:
        """Set up optional file caching and return cache name and uploaded files."""
        ...

    def cleanup_files(self, files: list[object], prefix: str) -> None:
        """Remove remote uploaded files."""
        ...
