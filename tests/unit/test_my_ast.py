# tests/unit/test_my_ast.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for coding_tools.my_ast."""

import ast
from pathlib import Path

import pytest

from coding_tools.my_ast import uncov_map


def test_uncov_map_non_existent_file(tmp_path: Path) -> None:
    """Test uncov_map with a non-existent file."""
    non_existent = tmp_path / "does_not_exist.py"
    assert uncov_map(non_existent, [1, 2]) == {}


def test_uncov_map_empty_lines(tmp_path: Path) -> None:
    """Test uncov_map with empty lines."""
    src = tmp_path / "sample.py"
    src.write_text("x = 1\n", encoding="utf-8")
    assert uncov_map(src, []) == {}


def test_uncov_map_syntax_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test uncov_map handling a file with syntax errors."""
    src = tmp_path / "bad.py"
    src.write_text("def broken(\n", encoding="utf-8")
    result = uncov_map(src, [1])
    assert result == {}


def test_ast_node_mapper_constructs(tmp_path: Path) -> None:
    """Test uncov_map with various AST node constructs."""
    code = (
        "class MyClass:\n"
        "    def my_method(self, x):\n"
        "        if x > 0:\n"
        "            for i in range(x):\n"
        "                while i > 0:\n"
        "                    try:\n"
        "                        raise ValueError()\n"
        "                    except ValueError:\n"
        "                        pass\n"
        "        else:\n"
        "            pass\n"
    )
    src = tmp_path / "sample.py"
    src.write_text(code, encoding="utf-8")

    target_lines = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    mappings = uncov_map(src, target_lines)
    assert len(mappings) > 0


def test_async_function_and_unparse_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test uncov_map with async functions and unparse failures."""
    code = (
        "async def async_func():\n"
        "    if (lambda: True)():\n"
        "        pass\n"
    )
    src = tmp_path / "async_sample.py"
    src.write_text(
        code,
        encoding="utf-8",
    )

    def mock_unparse(node: ast.AST) -> str:
        msg = "Mock unparse fail"
        raise ValueError(msg)

    monkeypatch.setattr(ast, "unparse", mock_unparse)
    mappings = uncov_map(src, [1, 2])
    assert 1 in mappings
    assert 2 in mappings


def test_all_constructs_fully(tmp_path: Path) -> None:
    """Test uncov_map covering all constructs."""
    code = (
        "while False:\n"
        "    pass\n"
        "try:\n"
        "    x = 1\n"
        "except Exception:\n"
        "    pass\n"
    )
    src = tmp_path / "full.py"
    src.write_text(code, encoding="utf-8")
    mappings = uncov_map(src, [1, 3, 5])
    assert len(mappings) >= 3
