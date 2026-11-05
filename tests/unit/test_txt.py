# tests/unit/test_txt.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for text tools."""

from coding_tools.txt import insert


def test_insert() -> None:
    """Test insert function."""
    txt = "line1\nline2\nline3"
    result = insert(txt, "new_line\n", 2)
    assert result == "line1\nnew_line\nline2\nline3"
