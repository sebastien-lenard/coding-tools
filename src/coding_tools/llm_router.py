# src/coding_tools/llm_router.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Map LLM models to fit client adapters based on config and import."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from coding_tools.conf import get_default_model, get_provider_mapping

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol

from coding_tools import my_logger

logger = my_logger.logger(__name__)


def get_llm_client(model_name: str | None = None) -> LLMClientProtocol:
    """Get LLM client map to target model via config and dynamic import.

    Check provider map. Use default model if model name is none. Raise ValueError
    if model not found in conf. Use importlib to load adapter class.
    """
    target_model = model_name if model_name is not None else get_default_model()
    providers = get_provider_mapping()

    for provider_info in providers.values():
        supported_models = provider_info.get("models", [])
        if target_model in supported_models or target_model.lower() in [
            m.lower() for m in supported_models
        ]:
            adapter_path = provider_info.get("adapter")
            if not adapter_path:
                continue
            module_str, class_str = adapter_path.split(":")
            module = importlib.import_module(module_str)
            adapter_class = getattr(module, class_str)
            return adapter_class(model_name=target_model)

    msg = f"Unsupported LLM model or model not found in provider config: {target_model}"
    logger.error(None, msg)
    raise ValueError(msg)
