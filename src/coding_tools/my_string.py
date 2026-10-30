# src/coding_tools/my_string.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
def my_str(txt: object | None) -> str:
    return str(txt) if txt else ""
