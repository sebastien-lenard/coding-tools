# src/coding_tools/txt.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
def insert(txt: str, new_info: str, line: int) -> str:
    """Insert new info in txt.

    Lines start with 1.
    """
    lines = txt.splitlines(keepends=True)
    lines.insert(line - 1, new_info)
    return "".join(lines)
