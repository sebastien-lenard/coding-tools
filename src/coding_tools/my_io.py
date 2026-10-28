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
    path = Path(path)

    if not path.exists() or not path.exists():
        logger.warning(None, f"No {path}")
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.exception(None, f"Failed to read {path}")
        return []
    return lines


def read_toml(
    path: Path | str,
) -> (
    dict[
        str,
        str | int | float | bool | dict | list | dt.datetime | dt.date | dt.time,
    ]
    | None
):
    path = Path(path)
    if not path.exists() or not path.exists():
        logger.warning(None, f"No {path}")
        return None
    return tomllib.loads(Path(path).read_bytes().decode("utf-8"))


def read_txt(path: Path | str) -> str:
    """Raises OSError, UnicodeEncodeError."""
    return Path(path).read_text(encoding="utf-8")


def write_txt(txt: str, path: Path | str) -> None:
    """Raises OSError, UnicodeEncodeError."""
    Path(path).write_text(txt, encoding="utf-8")
    logger.end(f"Txt saved to {path}")
