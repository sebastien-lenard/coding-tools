# tests/unit/test_my_io.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for my_io module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from coding_tools import my_io
from coding_tools.my_logger import Verbose


def test_dummy() -> None:
    """Test dummy assertion."""
    assert True


def test_save_llm_res_resp_error() -> None:
    """Test save_llm_req_resp with path error."""
    class BadPath:
        """Mock class that raises on fspath."""

        def __fspath__(self) -> str:
            msg = "Path error"
            raise RuntimeError(msg)

    with patch(
        "coding_tools.my_path.llm_log_path",
        side_effect=RuntimeError("Path error"),
    ):
        my_io.save_llm_req_resp(
            func="test_func",
            llm="test_llm",
            request="req",
            response="resp",
            target_file=Path("bad.py"), # type: ignore[arg-type]
        )


def test_save_llm_req_resp(tmp_path: Path) -> None:
    """Test save_llm_req_resp success."""
    target = tmp_path / "test.py"
    target.write_text("print('hi')", encoding="utf-8")
    with patch("coding_tools.my_path.llm_log_path") as mock_log_path:
        log_file = tmp_path / ".llm_logs" / "test_log.json"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        mock_log_path.return_value = log_file
        my_io.save_llm_req_resp(
            func="test_func",
            llm="test_llm",
            request="req",
            response="resp",
            target_file=target,
        )
        assert log_file.exists()


def test_read_lines(tmp_path: Path) -> None:
    """Test read_lines function."""
    f = tmp_path / "file.py"
    f.write_text("# comment\nline1\nline2\n", encoding="utf-8")
    lines = my_io.read_lines(f, header=True)
    assert "line1" in lines
    lines_no_header = my_io.read_lines(f, header=False)
    assert isinstance(lines_no_header, list)


def test_read_toml_success(tmp_path: Path) -> None:
    """Test read_toml success."""
    f = tmp_path / "config.toml"
    f.write_text('title = "TOML Example"\n', encoding="utf-8")
    data = my_io.read_toml(f)
    assert data["title"] == "TOML Example"


def test_read_toml_decode_error(tmp_path: Path) -> None:
    """Test read_toml decode error."""
    f = tmp_path / "config.toml"
    f.write_text("invalid toml content [\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed TOML decoding"):
        my_io.read_toml(f)


def test_read_txt_errors(tmp_path: Path) -> None:
    """Test read_txt error handling."""
    missing = tmp_path / "missing.txt"
    with pytest.raises(RuntimeError):
        my_io.read_txt(missing, raise_err=True)

    with pytest.raises(RuntimeError):
        my_io.read_txt(missing, raise_err=True)

    # Test empty file with raise_err=True
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Empty file"):
        my_io.read_txt(empty, raise_err=True)

    # Test empty file with raise_err=False
    assert my_io.read_txt(empty, raise_err=False) == ""


def test_write_txt_diff(tmp_path: Path) -> None:
    """Test write_txt with existing file diff."""
    f = tmp_path / "out.txt"
    f.write_text("old text\n", encoding="utf-8")
    my_io.write_txt("new text\n", f, verbose=Verbose.VV)
    assert f.read_text(encoding="utf-8") == "new text\n"


def test_write_txt_no_previous(tmp_path: Path) -> None:
    """Test write_txt with no previous file."""
    f = tmp_path / "brand_new.txt"
    my_io.write_txt("hello\n", f, verbose=Verbose.VV)
    assert f.read_text(encoding="utf-8") == "hello\n"
