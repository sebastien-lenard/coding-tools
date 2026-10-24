# src/coding_tools/logger.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Plain-text logging module enforcing strict formatting and anti-fluff standards."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Global prohibited fluff words to enforce lean phrasing
BANNED_WORDS = {"workflow", "execution", "engine", "successfully"}


def _sanitize(text: str) -> str:
    """Strip out unauthorized fluff words from log messages."""
    words = text.split()
    cleaned_words = [w for w in words if w.lower().strip(".,:;!?") not in BANNED_WORDS]
    return " ".join(cleaned_words)


class ProjectLogger:
    """Enforces uniform logging patterns, target contexts, and structure."""

    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)

    @staticmethod
    def _format_target(target: str | Path | None) -> str:
        """Extract filename without extension for target-specific log lines."""
        if not target:
            return ""
        path = Path(target)
        stem = path.stem if path.suffix == ".py" else path.name
        return f"{stem}: "

    def start(
        self,
        process_name: str,
        target: str | None = None,
        **details: Any,  # noqa: ANN401
    ) -> None:
        """Log process start with optional target context and nested parameters."""
        target_prefix = self._format_target(target)
        clean_process = _sanitize(process_name)
        self.logger.info("%sStart %s", target_prefix, clean_process)
        for key, value in details.items():
            detail_line = _sanitize(f"  - {key}: {value}")
            self.logger.info("%s", detail_line)

    def end(self, process_name: str, target: str | None = None) -> None:
        """Log process completion."""
        target_prefix = self._format_target(target)
        clean_process = _sanitize(process_name)
        self.logger.info("%sEnd %s.", target_prefix, clean_process)

    def progress(
        self,
        target: str | None,
        status: str,
        complementary_info: str = "",
    ) -> None:
        """Log routine progress and status updates."""
        target_prefix = self._format_target(target)
        clean_status = _sanitize(status)
        clean_info = _sanitize(complementary_info)
        separator = " " if clean_info else ""
        self.logger.info(
            "%s%s%s%s",
            target_prefix,
            clean_status,
            separator,
            clean_info,
        )

    def warning(self, target: str | None, message: str) -> None:
        """Log non-fatal unexpected warnings."""
        target_prefix = self._format_target(target)
        clean_msg = _sanitize(message)
        self.logger.warning("%s%s", target_prefix, clean_msg)

    def error(self, target: str | None, message: str) -> None:
        """Log fatal errors that halt processes."""
        target_prefix = self._format_target(target)
        clean_msg = _sanitize(message)
        self.logger.error("%s%s", target_prefix, clean_msg)

    def summary_table(
        self,
        title: str,
        headers: list[str],
        rows: list[list[str]],
    ) -> None:
        """Render multi-line summary table."""
        lines = [
            title,
            "---",
            " | ".join(headers),
            "---",
        ]
        lines.extend(" | ".join(str(cell) for cell in row) for row in rows)
        self.logger.info("\n%s", "\n".join(lines))

    def summary_line(
        self,
        title: str,
        headers: list[str],
        values: list[str],
    ) -> None:
        """Render compact single-line table summary."""
        lines = [
            title,
            "---",
            " | ".join(headers),
            "---",
            " | ".join(str(val) for val in values),
        ]
        self.logger.info("\n%s", "\n".join(lines))


def setup_logging() -> None:
    """Configure root logger to target sys.stderr with HH:MM:SS LEVEL layout."""
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def get_project_logger(name: str) -> ProjectLogger:
    """Instantiate and return a ProjectLogger instance for a given module."""
    return ProjectLogger(name)
