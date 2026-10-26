# src/coding_tools/my_logger.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Plain-text logging module applying formatting and anti-fluff."""

from __future__ import annotations

import logging
import sys
from enum import Enum, auto
from pathlib import Path
from typing import Any

# Global prohibited fluff words to enforce lean phrasing
BANNED_WORDS = {}


class RunState(Enum):
    """Stage of the run of a function or method."""

    START = auto()
    LIVE = auto()
    DONE = auto()
    FAIL = auto()
    SUCCESS = auto()


def _clean(text: str) -> str:
    """Strip out fluff words from logs."""
    if not BANNED_WORDS:
        return text
    words = text.split()
    cleaned_words = [w for w in words if w.lower().strip(".,:;!?") not in BANNED_WORDS]
    return " ".join(cleaned_words)


class MyLogger:
    """Applies uniform logging patterns, target contexts, and form."""

    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)

    @staticmethod
    def _format_target(target: str | Path | None, *, full_path: bool = False) -> str:
        """Get filename or full path for target-specific log lines."""
        if not target:
            return ""
        path = Path(target)
        if path.is_dir():
            return ""
        if full_path:
            return f"{path}: "
        stem = path.stem if path.suffix == ".py" else path.name
        return f"{stem}: " if stem else ""

    def start(
        self,
        process_name: str,
        target: str | Path | None = None,
        **details: Any,  # noqa: ANN401
    ) -> None:
        """Log process start with optional target context and nested params."""
        step = self._format_target(target)
        clean_process = _clean(process_name)
        self.logger.info("%sStart %s", step, clean_process)
        for key, value in details.items():
            detail_line = _clean(f"  {key}: {value}")
            self.logger.info("%s", detail_line)

    def end(self, process_name: str, target: str | Path | None = None) -> None:
        """Log process end."""
        step = self._format_target(target)
        clean_process = _clean(process_name)
        self.logger.info("%sEnd %s", step, clean_process)

    def progress(
        self,
        target: str | Path | None,
        status: str,
        supp_msg: str = "",
        *,
        full_path: bool = False,
    ) -> None:
        """Log progress and status updates."""
        step = self._format_target(target, full_path=full_path)
        clean_status = _clean(status)
        clean_info = _clean(supp_msg)
        separator = " " if clean_info else ""
        self.logger.info(
            "%s%s%s%s",
            step,
            clean_status,
            separator,
            clean_info,
        )

    def warning(
        self,
        target: str | Path | None,
        message: str,
        *,
        full_path: bool = False,
    ) -> None:
        """Log non-fatal unexpected warnings."""
        step = self._format_target(target, full_path=full_path)
        clean_msg = _clean(message)
        self.logger.warning("%s%s", step, clean_msg)

    def error(
        self,
        target: str | Path | None,
        message: str,
        *,
        full_path: bool = False,
    ) -> None:
        """Log fatal errors that halt processes."""
        step = self._format_target(target, full_path=full_path)
        clean_msg = _clean(message)
        self.logger.error("%s%s", step, clean_msg)

    def exception(
        self,
        target: str | Path | None,
        message: str,
        *,
        full_path: bool = False,
    ) -> None:
        """Log fatal error with exception traceback."""
        step = self._format_target(target, full_path=full_path)
        clean_msg = _clean(message)
        self.logger.exception("%s%s", step, clean_msg)  # noqa: LOG004

    def summary_table(
        self,
        title: str,
        headers: list[str],
        rows: list[list[str]],
    ) -> None:
        """Print multi-line summary table."""
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
        """Print single-line table summary."""
        lines = [
            title,
            "---",
            " | ".join(headers),
            "---",
            " | ".join(str(val) for val in values),
        ]
        self.logger.info("\n%s", "\n".join(lines))


def setup() -> None:
    """Set up root logger to target sys.stderr with HH:MM:SS LEVEL layout."""
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


def logger(name: str) -> MyLogger:
    """Create and return a MyLogger object for a module."""
    return MyLogger(name)
