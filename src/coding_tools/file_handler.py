# src/coding_tools/file_handler.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Centralized file and path management for tool outputs, logs, and coverage."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

COVERAGE_ANNOTATIONS_DIR = ".coverage_annotations"
PYTEST_OUTPUT_DIR = ".pytest_output"
PYRIGHT_OUTPUT_DIR = ".pyright_output"
RUFF_OUTPUT_DIR = ".ruff_output"

ALL_TOOL_OUTPUT_DIRS = {
    COVERAGE_ANNOTATIONS_DIR,
    PYTEST_OUTPUT_DIR,
    PYRIGHT_OUTPUT_DIR,
    RUFF_OUTPUT_DIR,
}


def ensure_directory(dir_path: str | Path) -> Path:
    """Ensure a target directory exists and return its Path object."""
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_pytest_log_path(test_file_path: str | Path) -> Path:
    """Return the calculated path for a pytest execution log file."""
    test_stem = Path(test_file_path).stem
    return ensure_directory(PYTEST_OUTPUT_DIR) / f"unit-test-{test_stem}.txt"


def get_basedpyright_log_path(test_file_path: str | Path) -> Path:
    """Return the calculated path for a basedpyright execution log file."""
    test_stem = Path(test_file_path).stem
    return ensure_directory(PYRIGHT_OUTPUT_DIR) / f"based-pyright-{test_stem}.txt"


def get_ruff_log_path(test_file_path: str | Path) -> Path:
    """Return the calculated path for a ruff execution log file."""
    test_stem = Path(test_file_path).stem
    return ensure_directory(RUFF_OUTPUT_DIR) / f"ruff-{test_stem}.txt"


def get_coverage_annotation_path(source_file_path: str | Path) -> Path:
    """Return the calculated path for a coverage annotated source file."""
    source_path = Path(source_file_path)
    cov_dir = ensure_directory(COVERAGE_ANNOTATIONS_DIR)
    return cov_dir / f"{source_path.name},cover"
