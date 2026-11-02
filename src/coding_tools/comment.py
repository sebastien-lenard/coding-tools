# src/coding_tools/comment.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
import re
from enum import Enum
from pathlib import Path
from typing import Final

from coding_tools import my_io, my_path

_LICENSE_DIR = "LICENSES"
_NOTICE_PATH = "NOTICE"

_HTML_HEAD = re.compile(r"^(?:[ \t]*<!--.*?-->[ \t]*\s*)+", flags=re.DOTALL)
_PYTHON_HEAD = re.compile(
    r"^(?:[ \t]*#(?!\s*!)(?!.*coding[=:]).*?\n|[ \t]*\n)*",
)

_PYTHON_INSERT_HEAD = re.compile(
    r"^(?:[ \t]*#\![^\n]*\n?|[ \t]*#.*coding[=:][^\n]*\n?)*",
    flags=re.IGNORECASE,
)


_EXT_SYSTEM: Final[dict[str, str]] = {
    ".html": ".html",
    ".py": ".py",
    ".md": ".html",
    ".md.example": ".html",
}

_SYSTEM_CONFIG: Final[dict[str, tuple[str, re.Pattern[str]]]] = {
    ".html": (
        "<!--TXT-->\n",
        re.compile(r"^[ \t]*(?:<!--.*-->)?$"),
    ),
    ".py": (
        "# TXT\n",
        re.compile(r"^[ \t]*(?:#.*)?$"),
    ),
}


_COPYRIGHT_PAT = re.compile(
    r"^Copyright\s+\d{4}\s+(.{5,})",
    flags=re.IGNORECASE | re.MULTILINE,
)
_SPDX_COPYRIGHT = "SPDX-FileCopyrightText: TXT"
_SPDX_LICENSE = "SPDX-License-Identifier: TXT"

_PATH_AND_LICENSE = re.compile(
    r"^[ \t]*(?:#[ \t]*SPDX-FileCopyrightText:.*|"
    r"#[ \t]*SPDX-License-Identifier:.*|"
    r"#[ \t]*[^/\n]+(?:/[^/\n]+)*\.[a-zA-Z0-9]+)\r?\n?",
    flags=re.MULTILINE,
)


class HeaderState(Enum):
    """State of file comments header.

    PASS or FAIL.
    """

    PASS = "Good header"  # noqa: S105
    FAIL = "Bad header"


def comment(txt: str, ext: str) -> str:
    """Wrap text in comments based on extension.

    Return "" if extension is unknown.
    """
    if system := _EXT_SYSTEM.get(ext):
        template, _ = _SYSTEM_CONFIG[system]
        return template.replace("TXT", txt)
    return ""


def head(txt: str) -> str:
    """Get comment header from html or python text.

    Return "" if no header found.
    """
    if (m := _HTML_HEAD.match(txt)) or (m := _PYTHON_HEAD.match(txt)):
        return m.group(0)
    return ""


def head_insert_line(txt: str) -> int:
    """Yield line number where inserting path and license comments.

    Line numbers start with 1
    """
    match = _PYTHON_INSERT_HEAD.match(txt)
    if match:
        header_part = match.group(0)
        if header_part:
            return header_part.count("\n") + 1

    return 1


def is_comment_or_blank(txt: str, ext: str) -> bool:
    if (system := _EXT_SYSTEM.get(ext)) and (pat := _SYSTEM_CONFIG[system][1]):
        return all(pat.match(line) for line in txt.splitlines())
    return False


def spdx_copyright(base_dir: Path | str, ext: str) -> str:
    """Extract SPDX copyright line from NOTICE file in base_dir."""
    notice_file = Path(base_dir) / _NOTICE_PATH
    try:
        content = my_io.read_txt(notice_file, header=False)
    except (FileNotFoundError, RuntimeError, ValueError) as err:
        msg = f"Missing NOTICE file at {notice_file}"
        raise RuntimeError(msg) from err

    if m := _COPYRIGHT_PAT.search(content):
        line = m.group(0).strip()
        clean_line = line.removeprefix("Copyright ").strip()
        return comment(f"{_SPDX_COPYRIGHT}".replace("TXT", clean_line), ext)

    msg = f"No copyright line found in {notice_file}"
    raise ValueError(msg)


def spdx_license(base_dir: Path | str, ext: str) -> str:
    """Extract SPDX license line from first file in base_dir/LICENSES."""
    licenses_dir = Path(base_dir) / _LICENSE_DIR
    try:
        license_file = my_path.files(licenses_dir, ext=None)[0]
    except Exception as err:
        msg = f"Missing LICENSES file at {licenses_dir}"
        raise FileNotFoundError(msg) from err

    license_id = license_file.stem
    return comment(f"{_SPDX_LICENSE}".replace("TXT", license_id), ext)


def strip_head(txt: str) -> str:
    """Strip comment headers from html or python text.

    Full False: Skip shebang (lines starting with #!) and encoding (lines containing
    coding: or coding=)
    """
    txt = _HTML_HEAD.sub("", txt)
    return _PYTHON_HEAD.sub("", txt)


def strip_path_and_license(txt: str) -> str:
    return _PATH_AND_LICENSE.sub("", txt).lstrip("\n")
