# src/coding_tools/pytest_cov.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Scan gaps in pytest coverage annotation files and build hints for LLM."""

from __future__ import annotations

import re
from pathlib import Path

import coding_tools.file_handler as my_path
from coding_tools import my_ast, my_io, my_logger

logger = my_logger.logger(__name__)

DEFAULT_COVERAGE_REPORT = (
    "--- Programmatic Branch & Coverage Analysis ---\n"
    "The test suite failed to achieve 100% coverage due to the "
    "following coverage gaps:\n\n"
    "### Uncovered Statements\n- None identified.\n\n"
    "### Unconditional / Partial Branch Jumps\n- None identified."
)
MAX_TEMPLATE_PARTS = 3
MAX_SUBTEMPLATE_PARTS = 2
TEMPLATE_PATH = Path("config/templates/cov_tips.md")
SNIPPET_CONTEXT_OFFSET = 3
SNIPPET_END_OFFSET = 2


def _get_default_report() -> str:
    """Return default coverage analysis report string."""
    return DEFAULT_COVERAGE_REPORT


def _read_input(
    src_file_path: str | Path,
) -> tuple[list[str], list[str]]:
    """Read src and pytest coverage annotation lines."""
    src_lines = my_io.read_lines(src_file_path)
    if not src_lines:
        logger.error(src_file_path, "Failed to read src file")
        return [], []
    cov_path = my_path.pytest_cov_path(src_file_path)
    if not cov_path:
        return src_lines, []
    cover_lines = my_io.read_lines(cov_path)
    if not cover_lines:
        logger.warning(None, f"No lines read from cov path: {cov_path}")
        return src_lines, []
    return src_lines, cover_lines


def _spot_cov_issues(
    cov_lines: list[str],
) -> tuple[list[int], list[tuple[int, str]]]:
    """Spot statements and branches uncovered by unit tests.

    Scan pytest coverage file lines.
    """
    uncov_lines: list[int] = []
    branch_notes: list[tuple[int, str]] = []

    for idx, line in enumerate(cov_lines):
        line_num = idx + 1
        if line.startswith("!"):
            uncov_lines.append(line_num)
        elif "no branch" in line.lower() or re.search(r"\d+->\d+", line):
            branch_notes.append((line_num, line.strip()))

    logger.progress(
        None,
        "Spotted coverage issues",
        f"uncovered statements: {len(uncov_lines)}, branch notes: {len(branch_notes)}",
    )

    return uncov_lines, branch_notes


def _parse_branch_audit(audit_line: str) -> str:
    """Turn raw coverage branch line into audit text."""
    lower_line = audit_line.lower()
    if "no branch" in lower_line:
        return "Branch was run, but branching paths never crossed in both ways."

    match = re.search(r"(\d+)->(exit|\d+)", audit_line)
    if match:
        target = match.group(2)
        if target == "exit":
            return "Branch jump exited early; the other branch path was never taken."
        return f"Branch jump to line {target} was never taken; tests only ran one way."

    return f"Partial branch test coverage jump: {audit_line}"


def _fmt_statements(
    src_lines: list[str],
    uncovered_lines: list[int],
    ast_map: dict[int, tuple[str, str]],
    stmt_template: str,
) -> list[str]:
    """Format uncovered statement template items."""
    stmt_items: list[str] = []
    for line_num in uncovered_lines:
        if line_num > len(src_lines):
            continue

        start_idx = max(0, line_num - SNIPPET_CONTEXT_OFFSET)
        end_idx = min(len(src_lines), line_num + SNIPPET_END_OFFSET)
        snippet_lines = src_lines[start_idx:end_idx]
        context_snippet = "\n".join(snippet_lines)

        func_name, audit_msg = ast_map.get(
            line_num,
            ("module scope", "Uncovered source statement."),
        )

        formatted_stmt = stmt_template.format(
            context_snippet=context_snippet,
            function_name=func_name,
            audit_msg=audit_msg,
        )
        stmt_items.append(formatted_stmt)
    return stmt_items


def _fmt_branches(
    src_lines: list[str],
    branch_notes: list[tuple[int, str]],
    ast_map: dict[int, tuple[str, str]],
    branch_template: str,
) -> list[str]:
    """Pen branch jump template items with AST context."""
    branch_items: list[str] = []
    for line_num, audit in branch_notes:
        start_idx = max(0, line_num - SNIPPET_CONTEXT_OFFSET)
        end_idx = min(len(src_lines), line_num + SNIPPET_END_OFFSET)
        branch_snippet = "\n".join(src_lines[start_idx:end_idx]) if src_lines else audit

        func_name, _ = ast_map.get(
            line_num,
            ("conditional block", "Partial branch coverage."),
        )
        descriptive_audit = _parse_branch_audit(audit)

        formatted_branch = branch_template.format(
            branch_snippet=branch_snippet,
            function_name=func_name,
            audit=descriptive_audit,
        )
        branch_items.append(formatted_branch)
    return branch_items


def tips(src_file_path: str | Path) -> str:
    """Scan pytest cov annotation file and build tips to address cov gaps.

    Fill template from config/templates/cov_tips.md with cov info from annotations.
    """
    func = f"{__name__}"
    logger.start(func, target=src_file_path)
    src_lines, cover_lines = _read_input(src_file_path)
    if not src_lines or not TEMPLATE_PATH.exists():
        logger.warning(
            src_file_path,
            "Missing source or template file, using default report",
        )
        logger.end(func, target=src_file_path)
        return _get_default_report()

    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    parts = template_text.split("--- Uncovered Statement Template ---")
    if len(parts) < MAX_SUBTEMPLATE_PARTS:
        logger.error(
            src_file_path,
            "Template structure invalid or missing statement template separator",
        )
        logger.end(func, target=src_file_path)
        return _get_default_report()

    main_header_template = parts[0].strip()
    sub_parts = parts[1].split("--- Branch Jump Template ---")
    stmt_template = sub_parts[0].strip()

    branch_sub_parts = (
        sub_parts[1].split("--- Missing Coverage Template ---")
        if len(sub_parts) > 1
        else ["", ""]
    )
    branch_template = branch_sub_parts[0].strip()
    missing_template = branch_sub_parts[1].strip() if len(branch_sub_parts) > 1 else ""

    if not cover_lines:
        logger.warning(
            src_file_path,
            "No coverage annotation report found, using missing coverage template",
        )
        logger.end(func, target=src_file_path)
        if missing_template:
            missing_body = missing_template.format(source_file=Path(src_file_path).name)
            return f"--- Programmatic Branch & Coverage Analysis ---\n\n{missing_body}"
        return _get_default_report()

    uncovered_lines, branch_notes = _spot_cov_issues(cover_lines)
    all_target_lines = uncovered_lines + [ln for ln, _ in branch_notes]
    ast_map = my_ast.uncov_map(src_file_path, all_target_lines)

    stmt_items = _fmt_statements(
        src_lines,
        uncovered_lines,
        ast_map,
        stmt_template,
    )
    branch_items = _fmt_branches(src_lines, branch_notes, ast_map, branch_template)

    uncov_body = "\n\n".join(stmt_items) if stmt_items else "- None identified."
    branch_jumps_body = (
        "\n\n".join(branch_items) if branch_items else "- None identified."
    )

    logger.end(func, target=src_file_path)
    return main_header_template.format(
        uncovered_statements_body=uncov_body,
        branch_jumps_body=branch_jumps_body,
    )
