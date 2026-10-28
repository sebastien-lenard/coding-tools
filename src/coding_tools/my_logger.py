# src/coding_tools/my_logger.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Plain-text logging module applying formatting and anti-fluff."""

from __future__ import annotations

import logging
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

# Global prohibited fluff words to enforce lean phrasing
BANNED_WORDS = {}


def _clean(text: str) -> str:
    """Strip banned words from log text."""
    if not BANNED_WORDS:
        return text
    words = text.split()
    cleaned_words = [w for w in words if w.lower().strip(".,:;!?") not in BANNED_WORDS]
    return " ".join(cleaned_words)


class MyLogger:
    """Wrap standard logging with target path formatting and anti-fluff."""

    def __init__(self, name: str) -> None:
        """Get logger instance by name."""
        self.logger = logging.getLogger(name)

    @staticmethod
    def _format_target(target: str | Path | None, *, full_path: bool = False) -> str:
        """Get filename or path for target log lines."""
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
        """Log non-fatal warning."""
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
        """Log fatal error."""
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
        """Log fatal error with traceback."""
        step = self._format_target(target, full_path=full_path)
        clean_msg = _clean(message)
        self.logger.exception("%s%s", step, clean_msg)  # noqa: LOG004

    @contextmanager
    def run_spin(self, message: str, prefix: str = "") -> Generator[None, None, None]:
        """Print inline dots in console during API wait.

        Writes to sys.stdout. Spawns daemon thread.
        """
        self.progress(prefix, message, "(waiting)")
        stop_event = threading.Event()

        def spin() -> None:
            """Loop and write dot to stdout until stop event set."""
            while not stop_event.is_set():
                sys.stdout.write(".")
                sys.stdout.flush()
                time.sleep(1)

        spinner_thread = threading.Thread(target=spin, daemon=True)
        spinner_thread.start()
        try:
            yield
        finally:
            stop_event.set()
            spinner_thread.join()
            sys.stdout.write("\n")
            sys.stdout.flush()

    def summary_table(
        self,
        title: str,
        columns: dict[str, str],
        rows: list[Any],
        formatters: dict[str, Any] | None = None,
    ) -> None:
        """Print multi-line summary table from objects or dicts using key map and formatters."""
        headers = list(columns.values())
        keys = list(columns.keys())
        formatters = formatters or {}

        formatted_rows = []
        for row in rows:
            row_cells = []
            for key in keys:
                if isinstance(row, dict):
                    val = row.get(key, "")
                else:
                    val = getattr(row, key, "")
                if key in formatters and val is not None:
                    val = formatters[key](val)
                row_cells.append(str(val) if val is not None else "")
            formatted_rows.append(row_cells)

        lines = [
            title,
            "---",
            " | ".join(headers),
            "---",
        ]
        lines.extend(" | ".join(cell) for cell in formatted_rows)
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
    """Set root logger to target sys.stderr with HH:MM:SS LEVEL layout."""
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
    """Get MyLogger object for module."""
    return MyLogger(name)
