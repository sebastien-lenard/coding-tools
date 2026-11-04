# tests/unit/test_conf.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for coding_tools.conf."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_tools.conf import (
    _strip_jsonc_comments,
    get_default_model,
    get_provider_mapping,
    load_llm_config,
    python_version,
    tools,
)


def test_strip_jsonc_comments() -> None:
    """Test stripping JSONC comments."""
    content = (
        "\n    {\n"
        "        // Single line comment\n"
        '        "default_model": "test-model", /* block comment */\n'
        '        "providers": {\n'
        "            // another comment\n"
        '            "gemini": {\n'
        '                "supports_caching": true\n'
        "            }\n"
        "        }\n"
        "    }\n"
        "    "
    )
    stripped = _strip_jsonc_comments(content)
    parsed = json.loads(stripped)
    assert parsed["default_model"] == "test-model"
    assert parsed["providers"]["gemini"]["supports_caching"] is True


def test_load_llm_config_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful loading of LLM config."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "llms.jsonc"
    config_file.write_text('{"default_model": "model-a"}', encoding="utf-8")

    cfg = load_llm_config()
    assert cfg["default_model"] == "model-a"


def test_load_llm_config_from_example(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test loading LLM config from example file."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    example_file = config_dir / "llms.jsonc.example"
    example_file.write_text(
        '{"default_model": "model-example"}',
        encoding="utf-8",
    )

    cfg = load_llm_config()
    assert cfg["default_model"] == "model-example"
    assert (config_dir / "llms.jsonc").exists()


def test_load_llm_config_missing_both(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error when both config and example are missing."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(
        FileNotFoundError,
        match=r"Missing LLM conf file and example\.",
    ):
        load_llm_config()


def test_load_llm_config_copy_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test OSError handling when copying from example config."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    example_file = config_dir / "llms.jsonc.example"
    example_file.write_text('{"default_model": "model-example"}', encoding="utf-8")

    def mock_write_text(*args: object, **kwargs: object) -> None:
        msg = "Disk full"
        raise OSError(msg)

    monkeypatch.setattr(Path, "write_text", mock_write_text)
    with pytest.raises(OSError, match="Disk full"):
        load_llm_config()


def test_load_llm_config_read_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test OSError handling when reading config file."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "llms.jsonc"
    config_file.write_text('{"default_model": "model-a"}', encoding="utf-8")

    def mock_read_text(*args: object, **kwargs: object) -> str:
        msg = "Read error"
        raise OSError(msg)

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    with pytest.raises(OSError, match="Read error"):
        load_llm_config()


def test_load_llm_config_json_decode_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test JSONDecodeError handling when parsing config file."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "llms.jsonc"
    config_file.write_text("invalid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_llm_config()


def test_get_default_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test getting default model from config."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "llms.jsonc"
    config_file.write_text('{"default_model": "custom-model"}', encoding="utf-8")

    assert get_default_model() == "custom-model"


def test_get_default_model_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test default model fallback when not specified."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "llms.jsonc"
    config_file.write_text("{}", encoding="utf-8")

    assert get_default_model() == "gemini-3.5-flash-lite"


def test_get_provider_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test getting provider mapping from config."""
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "conf" / "params"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "llms.jsonc"
    config_file.write_text(
        '{"providers": {"gemini": {"supports_caching": true}}}',
        encoding="utf-8",
    )

    mapping = get_provider_mapping()
    assert "gemini" in mapping
    assert mapping["gemini"]["supports_caching"] is True


def test_python_version_success(tmp_path: Path) -> None:
    """Test python_version extraction from pyproject.toml."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = ">=3.12"\n', encoding="utf-8")
    assert python_version(tmp_path) == ">=3.12"


def test_python_version_missing_fields(tmp_path: Path) -> None:
    """Test python_version when fields or file are missing."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("# empty\n", encoding="utf-8")
    assert python_version(tmp_path) is None
    pyproject.write_text("[other]\n", encoding="utf-8")
    assert python_version(tmp_path) is None
    pyproject.write_text("[project]\n", encoding="utf-8")
    assert python_version(tmp_path) is None


def test_tools_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test tools configuration loading from pyproject.toml."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.coding-tools.tools.my-tool]\nmod = "mymod"\nllm = "myllm"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    cfg = tools()
    assert "my-tool" in cfg
    assert cfg["my-tool"]["mod"] == "mymod"


def test_tools_missing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test tools configuration raises ValueError on missing key."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "foo"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=r"Missing tool.coding-tools.tools key"):
        tools()
