# src/coding_tools/llm_protocol.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Protocols, base models, and errors for LLM wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class for LLM errors."""


class LLMAPIError(LLMError):
    """Neutral API error mirror for provider bugs.

    Holds status code and error code from provider.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        """Set up API error with code and text.

        Saves status code and error code.
        """
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class LLMClientError(LLMError):
    """Neutral client error mirror for quota or bad request states.

    Holds retry flag and status code.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        """Set up client error with retry flag.

        Saves retryable state and status code.
        """
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class LLMServerError(LLMError):
    """Neutral server error mirror for retry state.

    Holds retry flag and status code.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        """Set up server error with retry flag.

        Saves retryable state and status code.
        """
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class LLMResponse(BaseModel):
    """Valid JSON schema for LLM output data.

    Has message and edited files strings.
    """

    message: str
    edited_files: str


@dataclass
class LLMCallParams:
    """Data bag for LLM text gen params.

    Holds schema, prefix, tool name, process step, and target file.
    """

    response_schema: type[BaseModel]
    prefix: str
    tool_name: str = "generic-tool"
    process_step: str = "generation"
    target_file: str = "unknown.py"


class LLMClientProtocol(Protocol):
    """Core rules for any LLM client adapter.

    Async call method returning LLMResponse.
    """

    async def call(
        self,
        req: str,
        params: LLMCallParams,
    ) -> LLMResponse:
        """Ask LLM API and check Pydantic model response.

        Async IO. Raises LLMError subclasses on fail.
        """
        ...
