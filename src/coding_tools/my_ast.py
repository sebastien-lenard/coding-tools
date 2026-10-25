# src/coding_tools/my_ast.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Audit source file AST and map line numbers to Python constructs."""

from __future__ import annotations

import ast
from pathlib import Path

from coding_tools.logger import get_project_logger

logger = get_project_logger(__name__)


class ASTNodeMapper(ast.NodeVisitor):
    """Audit map line numbers to AST constructs and functions."""

    def __init__(self, target_lines: list[int]) -> None:
        self.target_lines = set(target_lines)
        self.mappings: dict[int, tuple[str, str]] = {}
        self._current_function = "module scope"
        self._current_class = ""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Scan ClassDef node."""
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Scan FunctionDef node."""
        old_func = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_function = old_func

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Scan AsyncFunctionDef node."""
        old_func = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_func = old_func

    def _get_current_func_name(self) -> str:
        """Get formatted current function or method name."""
        return (
            f"{self._current_class}.{self._current_function}"
            if self._current_class
            else self._current_function
        )

    def visit_If(self, node: ast.If) -> None:
        """Scan If node."""
        lineno = getattr(node, "lineno", None)
        if (
            lineno is not None
            and lineno in self.target_lines
            and lineno not in self.mappings
        ):
            try:
                test_code = ast.unparse(node.test)
            except (SyntaxError, ValueError):
                test_code = "condition"
            self.mappings[lineno] = (
                self._get_current_func_name(),
                f"Uncovered `if` statement checking `{test_code}`.",
            )
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        """Scan Try node."""
        lineno = getattr(node, "lineno", None)
        if (
            lineno is not None
            and lineno in self.target_lines
            and lineno not in self.mappings
        ):
            self.mappings[lineno] = (
                self._get_current_func_name(),
                "Uncovered `try` block or exception handler.",
            )
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """Scan For node."""
        lineno = getattr(node, "lineno", None)
        if (
            lineno is not None
            and lineno in self.target_lines
            and lineno not in self.mappings
        ):
            self.mappings[lineno] = (
                self._get_current_func_name(),
                "Uncovered `for` loop construct.",
            )
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        """Scan While node."""
        lineno = getattr(node, "lineno", None)
        if (
            lineno is not None
            and lineno in self.target_lines
            and lineno not in self.mappings
        ):
            self.mappings[lineno] = (
                self._get_current_func_name(),
                "Uncovered `while` loop construct.",
            )
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        """Scan generic AST node."""
        lineno = getattr(node, "lineno", None)
        if (
            lineno is not None
            and lineno in self.target_lines
            and lineno not in self.mappings
        ):
            self.mappings[lineno] = (
                self._get_current_func_name(),
                f"Uncovered {type(node).__name__} statement.",
            )
        super().generic_visit(node)


def uncov_map(
    src_file_path: str | Path,
    uncov_lines: list[int],
) -> dict[int, tuple[str, str]]:
    """Audit source AST and return mapping of line numbers to (function, analysis)."""
    src_path = Path(src_file_path)
    if not src_path.exists() or not uncov_lines:
        return {}

    try:
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
    except SyntaxError:
        logger.exception(src_path, "Failed to parse source AST for mapping")
        return {}

    mapper = ASTNodeMapper(uncov_lines)
    mapper.visit(tree)
    return mapper.mappings
