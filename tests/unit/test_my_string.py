# tests/unit/test_my_string.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Test suite for my_string module."""

import pytest

from coding_tools.my_string import my_str


@pytest.mark.parametrize(
    ("txt", "expected"),
    [
        (None, ""),
        ("", ""),
        ("hello", "hello"),
        (123, "123"),
        (False, ""),
        (True, "True"),
    ],
)

def test_my_str(txt: object | None, expected: str) -> None:
    """Test my_str casts objects correctly or returns empty string."""
    assert my_str(txt) == expected
