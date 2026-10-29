# src/coding_tools/my_io.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import datetime as dt
import difflib
import tomllib
from pathlib import Path

from coding_tools import file_handler, my_logger

logger = my_logger.logger(__name__)


def read_lines(path: Path | str) -> list[str]:
    """Get lines from txt file."""
    return str(read_txt(path)).splitlines()


def read_toml(
    path: Path | str,
) -> (
    dict[
        str,
        str | int | float | bool | dict | list | dt.datetime | dt.date | dt.time,
    ]
    | None
):
    """Get dictionary from toml file."""
    txt = read_txt(path)
    try:
        return tomllib.loads(str(txt))
    except tomllib.TOMLDecodeError:
        logger.exception(None, f"Failed TOML decoding of {path}")
        return None


def read_txt(path: Path | str) -> str | None:
    """Raises OSError, UnicodeEncodeError."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.exception(None, f"Failed to read or decode file {path}")
        return None


def save_llm_req_resp(
    func: str,
    llm: str,
    request: str,
    response: str,
    target_file: Path | str | None = None,
) -> None:
    """Save llm request/responses structured LLM outputs as JSON.

    Saves to .llm_logs/ path.
    """
    try:
        log_path = file_handler.llm_log_path(
            input_path=target_file,
            func=func,
            llm=llm,
        )
        txt = (
            f"***Request***\n-------\n{request}\n\n***Response***\n-------\n{response}"
        )
        write_txt(txt, log_path)
        logger.progress(
            target_file,
            f"Done. LLM output file: {log_path}",
        )
    except Exception:
        logger.exception(
            target_file,
            "End. Failed to write LLM log",
        )


def write_txt(txt: str, path: Path | str) -> None:
    """Raises OSError, UnicodeEncodeError."""
    try:
        old_txt = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.progress(None, f"No previous file (or previous corrupted) {path}")
    else:
        old_lines = old_txt.splitlines(keepends=True)
        new_lines = txt.splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            ),
        )
        if diff:
            logger.progress(None, f"Diff:\n{''.join(diff)}")

    Path(path).write_text(txt, encoding="utf-8")
    logger.end(f"Txt saved to {path}")


def process_and_save_code(new_code: str, test_file_path: str, prefix: str) -> None:
    """Yield diff statistics, log diff, and write new test code.

    Uses unified diff and overwrites test file.
    """
    test_path = Path(test_file_path)
    old_code = test_path.read_text(encoding="utf-8")

    test_path.write_text(new_code, encoding="utf-8")
    logger.progress(prefix, f"Done. Saved script to {test_path}")
