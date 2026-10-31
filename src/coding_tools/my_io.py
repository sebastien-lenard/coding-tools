# src/coding_tools/my_io.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""IO tools to read and write files."""

from __future__ import annotations

import difflib
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime as dt

from coding_tools import comment, my_logger, my_path
from coding_tools.my_logger import Verbose

logger = my_logger.logger(__name__)


def read_lines(path: Path | str, *, header: bool = True) -> list[str]:
    """Get text lines from file.

    Calls read_txt. Raise RuntimeError, ValueError if file bad.
    """
    return str(read_txt(path, header=header)).splitlines()


def read_toml(
    path: Path | str,
) -> (
    dict[
        str,
        str | int | float | bool | dict | list | dt.datetime | dt.date | dt.time,
    ]
    | None
):
    """Get dict from TOML file.

    Calls tomllib.loads. Catch TOMLDecodeError, log and return None.
    """
    txt = read_txt(path)
    try:
        return tomllib.loads(str(txt))
    except tomllib.TOMLDecodeError:
        logger.exception(None, f"Failed TOML decoding of {path}")
        return None


def read_txt(path: Path | str, *, header: bool = True, raise_err: bool = True) -> str:
    """Read text from file with UTF-8.

    Catch OSError, UnicodeDecodeError. Raise RuntimeError if raise_err True. Strip
    workspace header if header False. Raise ValueError if text empty.
    """
    txt = ""
    try:
        txt = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        msg = f"No file (or corrupted) {path}"
        logger.exception(None, msg)
        if raise_err:
            raise RuntimeError(msg) from e
    if not header:
        txt = comment.strip_head(txt)
    if not txt:
        msg = f"Empty file {path}"
        logger.error(None, msg)
        if raise_err:
            raise ValueError(msg)
    return txt


def save_llm_req_resp(
    func: str,
    llm: str,
    request: str,
    response: str,
    target_file: Path | str | None = None,
) -> None:
    """Save LLM request and response pair to JSON log.

    Uses my_path.llm_log_path. Writes to .llm_logs/ path. Catch Exception and log.
    """
    try:
        log_path = my_path.llm_log_path(
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


def write_txt(txt: str, path: Path | str, verbose: Verbose = Verbose.V) -> None:
    """Write text to file with UTF-8 and diff check.

    Reads old file for unified diff if verbose VV. Saves to path and logs end.
    """
    try:
        old_txt = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        if verbose == Verbose.VV:
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
            if verbose == Verbose.VV:
                logger.progress(None, f"Diff:\n{''.join(diff)}")
            Path(path).write_text(txt, encoding="utf-8")
            logger.end(f"Txt saved to {path}")
            return

    Path(path).write_text(txt, encoding="utf-8")
    logger.end(f"Txt saved to {path}")
