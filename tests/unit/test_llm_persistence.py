# tests/unit/test_llm_persistence.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for llm_persistence.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import ANY, patch

import pytest
from pydantic import BaseModel

from coding_tools.llm_persistence import PersistOutputParameters, persist_llm_output
from coding_tools.llm_protocol import StructuredGenerationOptions

if TYPE_CHECKING:
    from pathlib import Path


class DummyModel(BaseModel):
    """Dummy model for testing validation."""

    value: str


@dataclass
class VariationParams:
    """Parameters for test variations."""

    parsed_model: DummyModel | None
    parsed_json: dict[str, Any] | None
    raw_text: str
    supports_caching: bool
    contents: list[str]


@pytest.mark.parametrize(
    "params_data",
    [
        VariationParams(
            parsed_model=DummyModel(value="model"),
            parsed_json=None,
            raw_text="raw",
            supports_caching=True,
            contents=["--- Target File: test.txt", "instruction 1"],
        ),
        VariationParams(
            parsed_model=None,
            parsed_json={"key": "json"},
            raw_text="raw",
            supports_caching=False,
            contents=["--- pyproject.toml", "instruction 2"],
        ),
        VariationParams(
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
    params_data: VariationParams,
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
        raw_text=params_data.raw_text,
        parsed_json=params_data.parsed_json,
        parsed_model=params_data.parsed_model,
        error_details=None,
        contents_list=list(params_data.contents),
        model_name="test-model",
        supports_caching=params_data.supports_caching,
    )

    with patch("coding_tools.llm_persistence.logger.progress") as mock_progress:
        persist_llm_output(params)
        assert mock_progress.called


def test_persist_llm_output_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that persistence exceptions are correctly logged via logger.exception."""
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

    with patch("coding_tools.llm_persistence.logger.exception") as mock_logger_exc:
        persist_llm_output(params)
        mock_logger_exc.assert_called_once_with(
            ANY,
            "End. Failed to write LLM output",
        )
