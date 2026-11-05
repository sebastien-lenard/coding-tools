# tests/unit/test_header.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for header check and format tools."""

from pathlib import Path

import pytest

from coding_tools import comment, header
from coding_tools.check import CheckParams
from coding_tools.my_run import EditState, RunOutput, RunState


def test_check_bad_file(tmp_path: Path) -> None:
    """Test check function with a bad file path."""
    run_output = RunOutput(func="header", status=RunState.PRESTART)
    res = header.check(
        CheckParams(old_txt="", new_txt="", file_path=tmp_path),
        run_output,
    )
    assert res.status == RunState.FAIL
    assert res.msg == "Bad file"


def test_check_unchanged_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test check function when the header remains unchanged."""
    py_file = tmp_path / "test.py"
    content = "# test.py\n"
    py_file.write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        comment,
        "spdx_copyright",
        lambda root_dir, suffix: "",
    )
    monkeypatch.setattr(
        comment,
        "spdx_license",
        lambda root_dir, suffix: "",
    )
    run_output = RunOutput(
        func="header",
        status=RunState.PRESTART,
        input_path=py_file,
        root_dir=tmp_path,
    )
    params = CheckParams(old_txt=content, new_txt="", file_path=py_file)
    res = header.check(params, run_output)
    assert res.status == RunState.PASS


def test_check_edited_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test check function when the header is edited."""
    py_file = tmp_path / "test.py"
    py_file.write_text("# Old header\n", encoding="utf-8")
    monkeypatch.setattr(
        comment,
        "spdx_copyright",
        lambda root_dir, suffix: "# SPDX-FileCopyrightText: 2026 Author\n",
    )
    monkeypatch.setattr(
        comment,
        "spdx_license",
        lambda root_dir, suffix: "# SPDX-License-Identifier: MIT\n",
    )
    run_output = RunOutput(
        func="header",
        status=RunState.PRESTART,
        input_path=py_file,
        root_dir=tmp_path,
    )
    params = CheckParams(old_txt="# Old header\n", new_txt="", file_path=py_file)
    res = header.check(params, run_output)
    assert res.status == RunState.PASS
    assert res.edited == EditState.EDITED


def test_check_value_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test check function raising ValueError on bad lines."""
    py_file = tmp_path / "test.py"
    content = "Not a comment line\n# test.py\n"
    py_file.write_text(content, encoding="utf-8")
    run_output = RunOutput(
        func="header",
        status=RunState.PRESTART,
        input_path=py_file,
        root_dir=tmp_path,
    )
    params = CheckParams(old_txt=content, new_txt="", file_path=py_file)
    monkeypatch.setattr(comment, "head", lambda text: "Not a comment line")
    monkeypatch.setattr(comment, "is_comment_or_blank", lambda line, suffix: False)
    with pytest.raises(ValueError, match="Bad txt with some lines other than comments"):
        header.check(params, run_output)


def test_precheck(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test precheck function with a header."""
    py_file = tmp_path / "test.py"
    py_file.write_text("# Old header\n", encoding="utf-8")
    monkeypatch.setattr(
        comment,
        "spdx_copyright",
        lambda root_dir, suffix: "# SPDX-FileCopyrightText: 2026 Author\n",
    )
    monkeypatch.setattr(
        comment,
        "spdx_license",
        lambda root_dir, suffix: "# SPDX-License-Identifier: MIT\n",
    )
    run_output = RunOutput(
        func="header",
        status=RunState.PRESTART,
        input_path=py_file,
        root_dir=tmp_path,
    )
    params = CheckParams(old_txt="# Old header\n", new_txt="", file_path=py_file)
    res = header.precheck(params, run_output)
    assert res.status == RunState.PASS
