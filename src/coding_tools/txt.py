# src/coding_tools/txt.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Text tools for text ops.

Safe helpers for base text types.
"""

def insert(txt: str, new_info: str, line: int) -> str:
    """Insert new info in txt at line.

    Lines start with 1. Split text, insert line, join.
    """
    lines = txt.splitlines(keepends=True)
    lines.insert(line - 1, new_info)
    return "".join(lines)
