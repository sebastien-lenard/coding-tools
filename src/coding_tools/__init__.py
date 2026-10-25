# src/coding_tools/__init__.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Export core tools for workspace backup, file handling, and stamping.

Exposes UntrackedBackupManager, WorkspaceStamper, and tool log path helpers.
"""

from .backup_untracked import UntrackedBackupManager
from .file_handler import (
    ALL_TOOL_OUTPUT_DIRS,
    get_basedpyright_log_path,
    get_pytest_log_path,
    get_ruff_log_path,
)
from .logger import setup_logging
from .workspace_stamper import WorkspaceStamper

__all__ = [
    "ALL_TOOL_OUTPUT_DIRS",
    "UntrackedBackupManager",
    "WorkspaceStamper",
    "get_basedpyright_log_path",
    "get_pytest_log_path",
    "get_ruff_log_path",
    "setup_logging",
]
