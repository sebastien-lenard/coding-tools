# src/coding_tools/my_time.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Sub process and time tools.

Safe helpers for date and time ops.
"""
from datetime import datetime


def now() -> tuple[int, str, str]:
    """Get stamp, date, and time now.

    Gets zone-aware datetime. Yields epoch int, YYYYMMDD string, HHMMSS string.
    """
    now = datetime.now().astimezone()
    return int(now.timestamp()), now.strftime("%Y%m%d"), now.strftime("%H%M%S")
