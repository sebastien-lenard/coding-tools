# src/coding_tools/config.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Load LLM config from JSONC files.

File I/O on config/parameters/llm_config.jsonc.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _strip_jsonc_comments(content: str) -> str:
    """Remove C-style block and line comments from JSONC string."""
    no_block = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    lines = []
    for line in no_block.splitlines():
        stripped_line = re.sub(r"\s*//.*$", "", line)
        lines.append(stripped_line)
    return "\n".join(lines)


def load_llm_config() -> dict[str, Any]:
    """Load LLM config from config/parameters/llm_config.jsonc.

    Copy from example if missing. Raise FileNotFoundError if both absent. File I/O.
    """
    config_path = Path("config/parameters/llm_config.jsonc")
    if not config_path.exists():
        example_path = Path("config/parameters/llm_config.jsonc.example")
        if example_path.exists():
            logger.info("Local llm_config.jsonc not found. Copying from example...")
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                example_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            msg = "Missing LLM configuration file and example."
            raise FileNotFoundError(msg)

    raw_content = config_path.read_text(encoding="utf-8")
    clean_json = _strip_jsonc_comments(raw_content)
    return json.loads(clean_json)


def get_default_model() -> str:
    """Get global default model name from config.

    Fallback to gemini-3.5-flash-lite if missing.
    """
    config = load_llm_config()
    return str(config.get("default_model", "gemini-3.5-flash-lite"))


def get_provider_mapping() -> dict[str, dict[str, Any]]:
    """Get provider adapters and compatible models mapping from config dict."""
    config = load_llm_config()
    return dict(config.get("providers", {}))


def is_caching_allowed(provider_name: str) -> bool:
    """Check if caching is supported by provider and enabled in config.

    Return false if either disabled or unsupported.
    """
    config = load_llm_config()
    user_enabled = bool(config.get("enable_caching", False))
    if not user_enabled:
        return False

    providers = get_provider_mapping()
    provider_info = providers.get(provider_name, {})
    return bool(provider_info.get("supports_caching", False))
