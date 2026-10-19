# src/coding_tools/llm_router.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Router module to instantiate the appropriate LLM client adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_tools.gemini_client import MODEL_NAME, GeminiClientAdapter

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol


def get_llm_client(model_name: str = MODEL_NAME) -> LLMClientProtocol:
    """Instantiate and return the appropriate LLM client adapter."""
    if "gemini" in model_name.lower() or model_name == MODEL_NAME:
        return GeminiClientAdapter()

    msg = f"Unsupported LLM model or provider specified: {model_name}"
    raise ValueError(msg)
