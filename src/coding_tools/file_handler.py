# src/coding_tools/file_handler.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Manage paths for tool outputs, logs, and coverage.

Writes files to disk (.coverage_annotations, .pytest_output, .pyright_output,
.ruff_output).
"""

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
    test_stem = Path(test_file_path).stem
    return ensure_directory(PYTEST_OUTPUT_DIR) / f"unit-test-{test_stem}.txt"


def get_basedpyright_log_path(test_file_path: str | Path) -> Path:
    """Get based-pyright log path.

    Creates .pyright_output if missing.
    """
    test_stem = Path(test_file_path).stem
    return ensure_directory(PYRIGHT_OUTPUT_DIR) / f"based-pyright-{test_stem}.txt"


def get_ruff_log_path(test_file_path: str | Path) -> Path:
    """Get ruff log path.

    Creates .ruff_output if missing.
    """
    test_stem = Path(test_file_path).stem
    return ensure_directory(RUFF_OUTPUT_DIR) / f"ruff-{test_stem}.txt"


def get_coverage_annotation_path(source_file_path: str | Path) -> Path:
    """Get coverage annotation path.

    Creates .coverage_annotations if missing.
    """
    source_path = Path(source_file_path)
    cov_dir = ensure_directory(COVERAGE_ANNOTATIONS_DIR)
    return cov_dir / f"{source_path.name},cover"
