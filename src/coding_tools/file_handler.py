# src/coding_tools/file_handler.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Manage paths for tool outputs, logs, and coverage.

Writes files to disk (.coverage_annotations, .pytest_output, .pyright_output,
.ruff_output, .llm_output).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

COVERAGE_ANNOTATIONS_DIR = ".coverage_annotations"
PYTEST_OUTPUT_DIR = ".pytest_output"
PYRIGHT_OUTPUT_DIR = ".pyright_output"
RUFF_OUTPUT_DIR = ".ruff_output"
LLM_OUTPUT_DIR = ".llm_output"

ALL_TOOL_OUTPUT_DIRS = {
    COVERAGE_ANNOTATIONS_DIR,
    PYTEST_OUTPUT_DIR,
    PYRIGHT_OUTPUT_DIR,
    RUFF_OUTPUT_DIR,
    LLM_OUTPUT_DIR,
}


@dataclass
class LLMOutputPathParameters:
    """Parameters for building LLM output paths."""

    llm_name: str
    start_date: str
    tool_name: str
    process_step: str
    target_file: str | Path
    status_label: str
    timestamp: int
    hhmiss: str


def ensure_directory(dir_path: str | Path) -> Path:
    """Create target directory if missing and return Path.

    Writes to disk.
    """
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_pytest_log_path(test_file_path: str | Path) -> Path:
    """Get pytest log path.

    Creates .pytest_output if missing.
    """
    base_dir = ensure_directory(PYTEST_OUTPUT_DIR)
    return base_dir / Path(test_file_path).name


def get_basedpyright_log_path(test_file_path: str | Path) -> Path:
    """Get based-pyright log path.

    Creates .pyright_output if missing.
    """
    base_dir = ensure_directory(PYRIGHT_OUTPUT_DIR)
    return base_dir / Path(test_file_path).name


def get_ruff_log_path(test_file_path: str | Path) -> Path:
    """Get ruff log path.

    Creates .ruff_output if missing.
    """
    base_dir = ensure_directory(RUFF_OUTPUT_DIR)
    return base_dir / Path(test_file_path).name


def get_coverage_annotation_path(source_file_path: str | Path) -> Path:
    """Get coverage annotation path.

    Creates .coverage_annotations if missing.
    """
    base_dir = ensure_directory(COVERAGE_ANNOTATIONS_DIR)
    return base_dir / Path(source_file_path).name


def get_llm_output_path(params: LLMOutputPathParameters) -> Path:
    """Get unique nested path for saving LLM execution outputs.

    Pattern: .llm_output/[llm name]/[yy-mm-dd]/[hhmiss]-[tool name]-[process step]-
    [target file]-[status]-[timestamp].json
    """
    sanitized_llm_name = (
        params.llm_name.replace("/", "-").replace("\\", "-").replace(":", "-")
    )
    target_filename = Path(params.target_file).name
    filename = (
        f"{params.hhmiss}-{params.tool_name}-{params.process_step}-"
        f"{target_filename}-{params.status_label}-{params.timestamp}.json"
    )

    dir_path = Path(LLM_OUTPUT_DIR) / sanitized_llm_name / params.start_date
    ensure_directory(dir_path)
    return dir_path / filename
