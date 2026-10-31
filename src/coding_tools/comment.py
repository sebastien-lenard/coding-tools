# src/coding_tools/comment.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

import re

_HTML_HEAD = re.compile(r"^(?:[ \t]*<!--.*?-->[ \t]*\s*)+", flags=re.DOTALL)
_PYTHON_HEAD = re.compile(r"^(?:[ \t]*#.*?\n|[ \t]*\n)*(?=[ \t]*\S)")


def strip_head(txt: str) -> str:
    txt = _HTML_HEAD.sub("", txt)
    return _PYTHON_HEAD.sub("", txt)
