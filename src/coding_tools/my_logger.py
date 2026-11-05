# src/coding_tools/my_logger.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Plain log print. Format text and drop fluff.

Uses std logging module. Filters text via BANNED_WORDS list.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from contextlib import contextmanager
from enum import Enum
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator, MutableMapping

# Global prohibited fluff words to enforce lean phrasing
BANNED_WORDS = {}
LEVELS = [logging.WARNING, logging.INFO, logging.DEBUG]

# ANSI color codes for terminal output
GREY = "\x1b[38;20m"
WHITE = "\x1b[37;20m"
YELLOW = "\x1b[33;20m"
RED = "\x1b[31;20m"
BOLD_RED = "\x1b[31;1m"
RESET = "\x1b[0m"


class Verbose(Enum):
    """Log rank set. V for base info, VV for more data.

    Base info logs warnings and main progress. Details log extra data.
    """

    V = "Log warnings and main progress"
    VV = "Log details"


def drop_pkg_name(mod_name: str) -> str:
    """Drop package name from module name.

    E.g. toto.blabla.lead return blabla.lead.
    """
    parts = mod_name.split(".", 1)
    return parts[1] if len(parts) > 1 else parts[0]


def set_level(logger: Logger, verbosity_count: int) -> None:
    """Set logger level, defaults to DEBUG if verbosity_count < 0."""
    index = max(0, min(verbosity_count, len(LEVELS) - 1))
    logger.setLevel(LEVELS[index])


def _clean(text: str) -> str:
    """Drop bad words from log text.

    Checks BANNED_WORDS set. Splits and strips punctuation from words.
    """
    if not BANNED_WORDS:
        return text
    words = text.split()
    cleaned_words = [w for w in words if w.lower().strip(".,:;!?") not in BANNED_WORDS]
    return " ".join(cleaned_words)


def summary_table(
    title: str,
    columns: dict[str, str],
    rows: list[Any],
    formatters: dict[str, Any] | None = None,
) -> str:
    """Get multi-line stats table from rows.

    Applies formatters to row values. Builds table lines and logs info.
    """
    headers = list(columns.values())
    keys = list(columns.keys())
    formatters = formatters or {}

    formatted_rows = []
    for row in rows:
        row_cells = []
        for key in keys:
            val = row.get(key, "") if isinstance(row, dict) else getattr(row, key, "")
            if key in formatters and val is not None:
                val = formatters[key](val)
            row_cells.append(str(val) if val else "")
        formatted_rows.append(row_cells)

    lines = [
        title,
        "---",
        " | ".join(headers),
        "---",
    ]
    lines.extend(" | ".join(cell) for cell in formatted_rows)
    return "\n".join(lines)


def summary_line(
    title: str,
    headers: list[str],
    values: list[str],
) -> str:
    """Get one-line stats table.

    Builds table headers and values line and logs info.
    """
    lines = [
        title,
        "---",
        " | ".join(headers),
        "---",
        " | ".join(str(val) for val in values),
    ]
    return "\n".join(lines)


class Formatter(logging.Formatter):
    """Log formatter."""

    def __init__(
        self,
        fmt: str = "%(asctime)s %(levelname)s: %(message)s",
        datefmt: str = "%H:%M:%S",
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.info_formatter = logging.Formatter(
            fmt="%(asctime)s: %(message)s",
            datefmt=datefmt,
        )
        self.formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s: %(message)s",
            datefmt=datefmt,
        )
        self.COLORS = {
            logging.DEBUG: GREY,
            logging.INFO: WHITE,
            logging.WARNING: YELLOW,
            logging.ERROR: RED,
            logging.CRITICAL: BOLD_RED,
        }

    def format(self, record: logging.LogRecord) -> str:
        """Format logs depending on extra options."""
        func_name = f"[{drop_pkg_name(record.name)}.{record.funcName}]"
        tool = getattr(record, "tool", "unknown tool")
        match getattr(record, "leg", None):
            case "start":
                record.msg = f"Start {tool} {func_name}"
            case "end":
                record.msg = f"End {tool} {func_name}"
            case "None":
                is_summary = isinstance(record.msg, str) and "\n" in record.msg
                is_trace = (
                    record.exc_info is not None or record.levelno >= logging.ERROR
                )
                if not is_summary and not is_trace and record.msg:
                    record.msg = f"{record.msg} {func_name}"

        txt = super().format(record)

        if record.levelno <= logging.INFO:
            txt = self.info_formatter.format(record)
        else:
            txt = self.formatter.format(record)

        color = self.COLORS.get(record.levelno, RESET)
        return f"{color}{txt}{RESET}"


class ContextAdapter(logging.LoggerAdapter):
    """Log context handler."""

    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        """Push extra new context info into the extra dict temporarily."""
        extra = dict(self.extra) if self.extra else {}

        call_extra = kwargs.get("extra")
        if isinstance(call_extra, dict):
            extra.update(call_extra)

        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str) -> ContextAdapter:
    """Return logger with extra dict."""
    return ContextAdapter(logging.getLogger(name), {})


class MyLogger:
    """Wrap std logging. Format target path and drop fluff.

    Uses logging module. Cleans text and formats target paths for log lines.
    """

    def __init__(self, name: str) -> None:
        """Get log base by name.

        Stores std logger instance.
        """
        self.logger = logging.getLogger(name)

    @staticmethod
    def _format_target(target: str | Path | None, *, full_path: bool = False) -> str:
        """Get file name or path for target log line.

        Skips directories. Uses stem for py files or full path if flag set.
        """
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
        """Log task start. Add target tag and dict items.

        Cleans process name and detail values. Logs info via std logger.
        """
        step = self._format_target(target)
        clean_process = _clean(process_name)
        self.logger.info("%sStart %s", step, clean_process)
        for key, value in details.items():
            detail_line = _clean(f"  {key}: {value}")
            self.logger.info("%s", detail_line)

    def end(self, process_name: str, target: str | Path | None = None) -> None:
        """Log task end.

        Cleans process name and logs info via std logger.
        """
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
        """Log step state and extra data.

        Cleans status and extra message text. Logs info via std logger.
        """
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
        """Log soft warning.

        Cleans message text. Logs warning via std logger.
        """
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
        """Log hard error.

        Cleans message text. Logs error via std logger.
        """
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
        """Log hard error with trace.

        Cleans message text. Logs exception via std logger.
        """
        step = self._format_target(target, full_path=full_path)
        clean_msg = _clean(message)
        self.logger.exception("%s%s", step, clean_msg)  # noqa: LOG004

    @contextmanager
    def run_spin(self, message: str, prefix: str = "") -> Generator[None, None, None]:
        """Print dot in console during API wait.

        Writes to sys.stdout. Spawns daemon thread with 1 second sleep.
        """
        self.progress(prefix, message, "(waiting)")
        stop_event = threading.Event()

        def spin() -> None:
            """Loop and write dot to stdout until stop flag set.

            Writes to sys.stdout and sleeps for 1 second.
            """
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
        """Log multi-line stats table from rows.

        Applies formatters to row values. Builds table lines and logs info.
        """
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
                row_cells.append(str(val) if val else "")
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
        """Print one-line stats table.

        Builds table headers and values line and logs info.
        """
        lines = [
            title,
            "---",
            " | ".join(headers),
            "---",
            " | ".join(str(val) for val in values),
        ]
        self.logger.info("\n%s", "\n".join(lines))


def setup() -> None:
    """Set root log stream to stderr with time format.

    Clears root log handlers and adds StreamHandler with time format and INFO level.
    """
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(Formatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def logger(name: str) -> MyLogger:
    """Get MyLogger object for module name.

    Returns new MyLogger instance with given name.
    """
    return MyLogger(name)
