# src/coding_tools/my_subprocess.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime


def now() -> tuple[int, str, str]:
    now = datetime.now().astimezone()
    return int(now.timestamp()), now.strftime("%Y%m%d"), now.strftime("%H%M%S")
