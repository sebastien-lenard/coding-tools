# tests/unit/test_llm_persistence.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for llm_persistence.py."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from coding_tools.llm_persistence import PersistOutputParameters, persist_llm_output
from coding_tools.llm_protocol import StructuredGenerationOptions


class DummyModel(BaseModel):
    """Dummy model for testing validation."""

    value: str


@dataclass
class TestVariation:
    """Container for test variation parameters to avoid PLR0917."""

    parsed_model: DummyModel | None
    parsed_json: dict[str, Any] | None
    raw_text: str
    supports_caching: bool
    contents: list[str]


@pytest.mark.parametrize(
    "variation",
    [
        TestVariation(
            parsed_model=DummyModel(value="model"),
            parsed_json=None,
            raw_text="raw",
            supports_caching=True,
            contents=["--- Target File: test.txt", "instruction 1"],
        ),
        TestVariation(
            parsed_model=None,
            parsed_json={"key": "json"},
            raw_text="raw",
            supports_caching=False,
            contents=["--- pyproject.toml", "instruction 2"],
        ),
        TestVariation(
            parsed_model=None,
            parsed_json=None,
            raw_text="raw text only",
            supports_caching=False,
            contents=["--- tests/conftest.py", "instruction 3"],
        ),
    ],
)
def test_persist_llm_output_variations(
    tmp_path: Path,
    variation: TestVariation,
) -> None:
    """Test persist_llm_output with various parameter combinations."""
    target_file = tmp_path / "test.txt"
    target_file.write_text("content", encoding="utf-8")

    options = StructuredGenerationOptions(
        tool_name="test_tool",
        process_step="step",
        target_file=str(target_file),
        system_instruction="sysinst",
        start_date="2026-01-01",
        prefix="TST",
        response_schema=DummyModel,
        spinner_msg="Processing...",
    )

    params = PersistOutputParameters(
        options=options,
        status_label="SUCCESS",
        raw_text=variation.raw_text,
        parsed_json=variation.parsed_json,
        parsed_model=variation.parsed_model,
        error_details=None,
        contents_list=list(variation.contents),
        model_name="test-model",
        supports_caching=variation.supports_caching,
    )

    persist_llm_output(params)


def test_persist_llm_output_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that persistence exceptions are correctly logged."""
    target_file = tmp_path / "test.txt"
    options = StructuredGenerationOptions(
        tool_name="test_tool",
        process_step="step",
        target_file=str(target_file),
        system_instruction="sysinst",
        start_date="2026-01-01",
        prefix="TST",
        response_schema=DummyModel,
        spinner_msg="Processing...",
    )
    params = PersistOutputParameters(
        options=options,
        status_label="ERROR",
        raw_text="err",
        parsed_json=None,
        parsed_model=None,
        error_details="some error",
        contents_list=[],
        model_name="test-model",
        supports_caching=True,
    )

    class DummyPath:
        """Dummy path object for simulating write failures."""

        def write_text(self, *_: object, **__: object) -> None:
            msg = "Forced write failure"
            raise RuntimeError(msg)

    def mock_get_llm_output_path(*_: object, **__: object) -> DummyPath:
        return DummyPath()

    monkeypatch.setattr(
        "coding_tools.llm_persistence.get_llm_output_path",
        mock_get_llm_output_path,
    )

    with caplog.at_level(logging.ERROR):
        persist_llm_output(params)

    assert any(
        "Failed to write LLM output dump" in record.message
        for record in caplog.records
    )


def test_persist_llm_output_success_logs_info(tmp_path: Path) -> None:
    """Test that successfully persisting LLM output logs an info message."""
    options = MagicMock()
    options.target_file = str(tmp_path / "target.py")
    options.prefix = "test-prefix"
    options.start_date = "2026-01-01"
    options.tool_name = "test-tool"
    options.process_step = "test-step"
    options.system_instruction = "instruction"

    params = PersistOutputParameters(
        options=options,
        status_label="SUCCESS",
        raw_text="hello world",
        parsed_json=None,
        parsed_model=None,
        error_details=None,
        contents_list=[],
        model_name="test-model",
        supports_caching=True,
    )

    mock_out_path = tmp_path / "output_dump.json"

    with (
        patch(
            "coding_tools.llm_persistence.get_llm_output_path",
            return_value=mock_out_path,
        ),
        patch.object(Path, "write_text"),
        patch("coding_tools.llm_persistence.logger.info") as mock_logger_info,
    ):
        persist_llm_output(params)

        mock_logger_info.assert_called_once_with(
            "[%s] Saved structured LLM output dump to %s",
            "test-prefix",
            mock_out_path,
        )


def test_persist_llm_output_exception_logs_error(tmp_path: Path) -> None:
    """Test that an exception during file write triggers logger.exception."""
    options = MagicMock()
    options.target_file = str(tmp_path / "target.py")
    options.prefix = "test-prefix"
    options.start_date = "2026-01-01"
    options.tool_name = "test-tool"
    options.process_step = "test-step"
    options.system_instruction = "instruction"

    params = PersistOutputParameters(
        options=options,
        status_label="SUCCESS",
        raw_text="hello world",
        parsed_json=None,
        parsed_model=None,
        error_details=None,
        contents_list=[],
        model_name="test-model",
        supports_caching=True,
    )

    mock_out_path = tmp_path / "output_dump.json"

    with (
        patch(
            "coding_tools.llm_persistence.get_llm_output_path",
            return_value=mock_out_path,
        ),
        patch.object(Path, "write_text", side_effect=OSError("Disk full")),
        patch("coding_tools.llm_persistence.logger.exception") as mock_logger_exc,
    ):
        persist_llm_output(params)

        mock_logger_exc.assert_called_once_with(
            "[%s] Failed to write LLM output dump",
            "test-prefix",
        )
