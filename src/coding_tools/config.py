# src/coding_tools/config.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Load LLM config from JSONC files.

File I/O on config/parameters/llm_config.jsonc.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from coding_tools import my_io, my_logger, my_path

logger = my_logger.logger(__name__)

PYPROJECT_TOML = "pyproject.toml"


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
            logger.progress(config_path, "Missing conf, copying from example")
            config_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                config_path.write_text(
                    example_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            except OSError:
                logger.exception(config_path, "Failed to copy conf")
                raise
        else:
            msg = "Missing LLM conf file and example."
            logger.error(config_path, msg)
            raise FileNotFoundError(msg)

    try:
        raw_content = config_path.read_text(encoding="utf-8")
    except OSError:
        logger.exception(config_path, "Failed to read conf")
        raise

    clean_json = _strip_jsonc_comments(raw_content)
    try:
        return json.loads(clean_json)
    except json.JSONDecodeError:
        logger.exception(config_path, "Failed to parse JSONC")
        raise


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


def python_version(path: Path | str) -> str | None:
    """Get the minimal Python version from pyproject.toml."""
    data = cast(
        "dict[str, Any]",
        my_io.read_toml(my_path.prj_root(path) / PYPROJECT_TOML),
    )
    if (
        not data
        or not data.get("project", {})
        or not data.get("project", {}).get("requires-python")
    ):
        return None
    return data.get("project", {}).get("requires-python")
