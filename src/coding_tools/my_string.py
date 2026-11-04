# src/coding_tools/my_string.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""String tools for text ops.

Safe helpers for base text types. No file writes or API calls.
"""


def my_str(txt: object | None) -> str:
    """Cast obj to str or give empty str if null.

    Safe check on input data type. Yields empty str if input is None or false.
    """
    return str(txt) if txt else ""
