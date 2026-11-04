# tests/unit/test_my_time.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for my_time module."""
from coding_tools import my_time


def test_now() -> None:
    """Test that now returns a valid timestamp, date string, and time string."""
    epoch, date_str, time_str = my_time.now()
    assert isinstance(epoch, int)
    assert isinstance(date_str, str)
    assert len(date_str) == 8
    assert date_str.isdigit()
    assert isinstance(time_str, str)
    assert len(time_str) == 6
    assert time_str.isdigit()
