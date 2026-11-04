# src/coding_tools/conf.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Load LLM config from JSONC files.

File I/O on conf/params/llms.jsonc.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from coding_tools import my_io, my_logger, my_path

logger = my_logger.logger(__name__)

PYPROJECT_TOML = "pyproject.toml"


class ToolConf(TypedDict):
    """Tool config map type.

    Has mod and llm keys.
    """

    mod: str
    llm: str


def _strip_jsonc_comments(content: str) -> str:
    """Strip C-style block and line tags from JSONC string.

    RegEx pass on text. Yield clean JSON string.
    """
    no_block = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    lines = []
    for line in no_block.splitlines():
        stripped_line = re.sub(r"\s*//.*$", "", line)
        lines.append(stripped_line)
    return "\n".join(lines)


def load_llm_config() -> dict[str, Any]:
    """Load LLM config from JSONC file.

    File I/O on conf/params/llms.jsonc. Copy from example if
    missing. Raise FileNotFoundError if both absent. Parse JSON via stdlib json.
    """
    config_path = Path("conf/params/llms.jsonc")
    if not config_path.exists():
        example_path = Path("conf/params/llms.jsonc.example")
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
    """Get global default model name from config dict.

    Fall back to gemini-3.5-flash-lite if key is not set.
    """
    config = load_llm_config()
    return str(config.get("default_model", "gemini-3.5-flash-lite"))


def get_provider_mapping() -> dict[str, dict[str, Any]]:
    """Get provider adapters and map models from config dict.

    Return dict of providers or empty dict.
    """
    config = load_llm_config()
    return dict(config.get("providers", {}))


def pyproject(path: Path | str | None = None) -> dict[str, Any]:
    """Read pyproject.toml and return dict data.

    File I/O on pyproject.toml. Raise RuntimeError or ValueError on bad path.
    """
    path = Path(PYPROJECT_TOML) if not path else my_path.root_dir(path) / PYPROJECT_TOML
    return my_io.read_toml(my_path.root_dir(path) / PYPROJECT_TOML)


def python_version(path: Path | str | None) -> str | None:
    """Get min Python version from pyproject.toml file.

    Read TOML via my_io. Read requires-python key under project block.
    Return None if key or file is absent.
    """
    data = pyproject(path)
    if (
        not data
        or not data.get("project", {})
        or not data.get("project", {}).get("requires-python")
    ):
        return None
    return data.get("project", {}).get("requires-python")


def tools() -> dict[str, ToolConf]:
    """Get tools configuration dictionary from pyproject.toml.

    File I/O on pyproject.toml. Raise ValueError if key is missing.
    """
    try:
        return pyproject()["tool"]["coding-tools"]["tools"]
    except KeyError as e:
        msg = "Missing tool.coding-tools.tools key in pyproject.toml"
        raise ValueError(msg) from e
