# src/coding_tools/my_io.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import datetime as dt
import tomllib
from pathlib import Path

from coding_tools import my_logger

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


def write_txt(txt: str, path: Path | str) -> None:
    """Raises OSError, UnicodeEncodeError."""
    Path(path).write_text(txt, encoding="utf-8")
    logger.end(f"Txt saved to {path}")
