# src/coding_tools/my_ast.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Scan source AST to map line numbers to Python constructs."""

from __future__ import annotations

import ast
from pathlib import Path

from coding_tools import my_logger

logger = my_logger.logger(__name__)


class ASTNodeMapper(ast.NodeVisitor):
    """Map line numbers to AST constructs.

    Inherit ast.NodeVisitor. Store target line matches in mappings dict.
    Track current class and function scope during traversal.
    """

    def __init__(self, target_lines: list[int]) -> None:
        """Set up mapper with target line set and empty mappings."""
        self.target_lines = set(target_lines)
        self.mappings: dict[int, tuple[str, str]] = {}
        self._current_function = "module scope"
        self._current_class = ""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit ClassDef, update scope, and walk child nodes."""
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit FunctionDef, update scope, and walk child nodes."""
        old_func = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_function = old_func

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit AsyncFunctionDef, update scope, and walk child nodes."""
        old_func = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_func = old_func

    def _get_current_func_name(self) -> str:
        """Get formatted current function or method name string."""
        return (
            f"{self._current_class}.{self._current_function}"
            if self._current_class
            else self._current_function
        )

    def visit_If(self, node: ast.If) -> None:
        """Map line to uncovered if statement if target line match."""
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
        """Map line to uncovered try block if target line match."""
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
        """Map line to uncovered for loop if target line match."""
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
        """Map line to uncovered while loop if target line match."""
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
        """Map line to generic node if target line match."""
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


def del_docstrings(tree: ast.AST) -> None:
    """Clear docstrings from AST nodes in place.

    Walk tree and pop first body expr if constant string.
    """
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module),
        ) and (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)


def match_codes(
    prev_code: str,
    new_code: str,
) -> bool:
    """Check if non-docstring code matches between two strings.

    False if syntax error, or if unparsed code trees differ.
    """
    func = f"{__name__}"
    logger.start(func)
    try:
        orig_tree = ast.parse(prev_code)
        new_tree = ast.parse(new_code)
    except SyntaxError:
        msg = "Bad code syntax (failed scan)"
        logger.exception(None, msg)
        return False

    del_docstrings(orig_tree)
    del_docstrings(new_tree)

    orig_normalized = ast.unparse(orig_tree)
    new_normalized = ast.unparse(new_tree)

    if orig_normalized != new_normalized:
        msg = "Spotted code edits"
        logger.warning(None, msg)
        return False

    logger.end(func)
    return True


def uncov_map(
    src_file_path: str | Path,
    uncov_lines: list[int],
) -> dict[int, tuple[str, str]]:
    """Audit source AST and return mapping of line numbers to analysis tuple.

    Read file from disk. Return empty dict if file missing or parse error.
    """
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
