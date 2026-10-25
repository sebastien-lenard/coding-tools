# src/coding_tools/llm_persistence.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Save LLM outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from coding_tools.file_handler import (
    LLMOutputPathParameters,
    get_llm_output_path,
    get_project_root,
)
from coding_tools.logger import get_project_logger

if TYPE_CHECKING:
    from pydantic import BaseModel

    from coding_tools.llm_protocol import StructuredGenerationOptions

logger = get_project_logger(__name__)


@dataclass
class PersistOutputParameters:
    """Hold parameters to save LLM outputs.

    Dataclass carrying options, status, payload variants, and cache flags.
    """

    options: StructuredGenerationOptions
    status_label: str
    raw_text: str | None
    parsed_json: Any | None
    parsed_model: BaseModel | None
    error_details: str | None
    contents_list: list[object]
    model_name: str
    supports_caching: bool


def persist_llm_output(params: PersistOutputParameters) -> None:
    """Write structured LLM outputs as JSON.

    Saves to .unit-test-tmp/ path based on timestamp and parameters. Writes file with
    UTF-8 encoding. Logs errors if write fails.
    """
    now_local = datetime.now(UTC).astimezone()
    timestamp = int(now_local.timestamp())
    hhmiss = now_local.strftime("%H%M%S")

    proj_root = get_project_root(params.options.target_file)

    max_reached_step = "raw_response"
    response_payload: Any = params.raw_text

    if params.parsed_model is not None:
        max_reached_step = "pydantic_validation"
        response_payload = params.parsed_model.model_dump()
    elif params.parsed_json is not None:
        max_reached_step = "json_parsing"
        response_payload = params.parsed_json

    file_contents: list[str] = []
    instructions: list[str] = []

    for item in params.contents_list:
        item_str = str(item)
        if (
            "--- Target File:" in item_str
            or "--- pyproject.toml" in item_str
            or "--- tests/conftest.py" in item_str
        ):
            file_contents.append(item_str)
        else:
            instructions.append(item_str)

    transferred_files = [str(params.options.target_file)]
    if not params.supports_caching:
        transferred_files.extend(
            [
                str(proj_root / "pyproject.toml"),
                str(proj_root / "tests/conftest.py"),
            ],
        )

    dump_data: dict[str, Any] = {
        "metadata": {
            "timestamp": timestamp,
            "hhmiss": hhmiss,
            "tool_name": params.options.tool_name,
            "process_step": params.options.process_step,
            "target_file": str(params.options.target_file),
            "transferred_files": transferred_files,
            "llm_name": params.model_name,
            "status": params.status_label,
        },
        "request": {
            "system_instruction": params.options.system_instruction,
            "file_contents": file_contents,
            "instructions_and_logs": instructions,
        },
        "response": {
            "max_reached_step": max_reached_step,
            "response_data": response_payload,
            "error_details": params.error_details,
        },
    }

    try:
        path_params = LLMOutputPathParameters(
            llm_name=params.model_name,
            start_date=params.options.start_date,
            tool_name=params.options.tool_name,
            process_step=params.options.process_step,
            target_file=params.options.target_file,
            status_label=params.status_label,
            timestamp=timestamp,
            hhmiss=hhmiss,
            project_root=proj_root,
        )
        out_path = get_llm_output_path(path_params)
        out_path.write_text(json.dumps(dump_data, indent=2), encoding="utf-8")
        logger.progress(
            params.options.target_file,
            f"Done. LLM output file: {out_path}",
        )
    except Exception:
        logger.exception(
            params.options.target_file,
            "End. Failed to write LLM output",
        )
