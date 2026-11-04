# tests/unit/test_comment.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Test comment module."""

from pathlib import Path

import pytest

from coding_tools import comment as comment_mod


def test_spdx_copyright(tmp_path: Path) -> None:
    """Test spdx_copyright extracts and formats copyright from NOTICE file."""
    notice = tmp_path / "NOTICE"
    notice.write_text("Copyright 2026 Author Name\nSome notice text", encoding="utf-8")
    assert "SPDX-FileCopyrightText: 2026 Author Name" in comment_mod.spdx_copyright(
        tmp_path,
        ".py",
    )


def test_spdx_copyright_errors(tmp_path: Path) -> None:
    """Test spdx_copyright handles missing NOTICE and missing copyright line."""
    with pytest.raises(RuntimeError):
        comment_mod.spdx_copyright(tmp_path, ".py")

    notice = tmp_path / "NOTICE"
    notice.write_text("No copyright here", encoding="utf-8")
    with pytest.raises(ValueError, match="No copyright line found"):
        comment_mod.spdx_copyright(tmp_path, ".py")


def test_spdx_license(tmp_path: Path) -> None:
    """Test spdx_license extracts license from LICENSES dir."""
    licenses = tmp_path / "LICENSES"
    licenses.mkdir()
    lic_file = licenses / "MIT.txt"
    lic_file.write_text("MIT License", encoding="utf-8")

    assert "SPDX-License-Identifier: MIT" in comment_mod.spdx_license(tmp_path, ".py")


def test_spdx_license_missing(tmp_path: Path) -> None:
    """Test spdx_license raises FileNotFoundError when dir missing."""
    with pytest.raises(FileNotFoundError):
        comment_mod.spdx_license(tmp_path, ".py")


def test_head_insert_line() -> None:
    """Test head_insert_line calculates the correct insertion index."""
    py_code = "#!/usr/bin/env python\n# coding: utf-8\n# Header\nprint('hi')"
    assert comment_mod.head_insert_line(py_code) == 3
    py_code_empty_header = "#!/usr/bin/env python\n# coding: utf-8"
    assert comment_mod.head_insert_line(py_code_empty_header) == 2

    # Covers if match: == False (no shebang/encoding at start)
    assert comment_mod.head_insert_line("x = 1\nprint('hi')") == 1

    # Covers if header_part: == False (empty start of text matching zero-length)
    assert comment_mod.head_insert_line("") == 1


def test_comment_and_head() -> None:
    """Test comment wrapping and head extraction."""
    assert comment_mod.comment("test", ".py") == "# test\n"
    assert comment_mod.comment("test", ".unknown") == ""

    py_code = "#!/usr/bin/env python\n# coding: utf-8\nprint('hi')"
    assert comment_mod.head(py_code) == "#!/usr/bin/env python\n# coding: utf-8\n"

    html_code = "<!-- Header -->\n<div></div>"
    assert comment_mod.head(html_code) == "<!-- Header -->\n"

    # Covers if (m := _HTML_HEAD.match(txt)) or (m := _PYTHON_HEAD.match(txt)): == False
    assert comment_mod.head("x = 1\nprint('hi')") == ""

    assert comment_mod.is_comment_or_blank("# comment\n", ".py") is True
    assert comment_mod.is_comment_or_blank("print('hi')", ".py") is False
    assert comment_mod.is_comment_or_blank("code", ".unknown") is False


def test_strip_functions() -> None:
    """Test stripping heads, paths, and licenses."""
    py_code = "# Header\n# SPDX-FileCopyrightText: 2026\n# src/foo.py\nprint('hi')"
    stripped = comment_mod.strip_path_and_license(py_code)
    assert "print('hi')" in stripped
    assert comment_mod.strip_head("") == ""
