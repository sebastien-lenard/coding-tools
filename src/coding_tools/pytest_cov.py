# src/coding_tools/pytest_cov.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Scan gaps in pytest coverage annotation files and build hints for LLM."""

from __future__ import annotations

import re
from dataclasses import replace
from enum import Enum
from pathlib import Path

from coding_tools import my_ast, my_io, my_logger, my_path
from coding_tools.my_run import RunOutput, RunState

logger = my_logger.logger(__name__)


class CovState(Enum):
    """Give presence or absence of unit tests that cover source."""

    FULL = "Fully covered"
    PARTLY = "Partly covered"
    MISSING = "No coverage"


BRIEF_MISSING = "No unit test seems to cover the source file"
MAX_TEMPLATE_PARTS = 3
MAX_SUBTEMPLATE_PARTS = 2
COV_STMT_TEMPL_PATH = Path("config/templates/cov_stmt.md")
COV_BRANCH_TEMPL_PATH = Path("config/templates/cov_branch.md")
SNIPPET_CONTEXT_OFFSET = 3
SNIPPET_END_OFFSET = 2


def issues(
    src_file_path: Path | str,
) -> tuple[list[int], list[tuple[int, str]], CovState, RunState]:
    uncov_lines: list[int] = []
    branch_notes: list[tuple[int, str]] = []
    try:
        ann_lines = my_io.read_lines(my_path.pytest_cov_path(src_file_path))
    except (FileNotFoundError, RuntimeError, ValueError):
        msg = (
            f"No cov file (or corrupted) for {src_file_path} in "
            f"{my_path.pytest_cov_dir(src_file_path)}"
        )
        logger.warning(None, msg)
        return uncov_lines, branch_notes, CovState.MISSING, RunState.FAIL

    for idx, line in enumerate(ann_lines):
        line_num = idx + 1
        if line.startswith("!"):
            uncov_lines.append(line_num)
        elif "no branch" in line.lower() or re.search(r"\d+->\d+", line):
            branch_notes.append((line_num, line.strip()))
    if not uncov_lines and not branch_notes:
        cov_status = CovState.FULL
        status = RunState.PASS
        logger.progress(
            None,
            "Spotted coverage issues",
            f"uncovered statements: {len(uncov_lines)}, branch notes: "
            f"{len(branch_notes)}",
        )
    else:
        cov_status = CovState.PARTLY
        status = RunState.FAIL

    return uncov_lines, branch_notes, cov_status, status


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


def _fmt_stmts(src_file_path: Path | str, uncovered_lines: list[int]) -> str:
    """Format uncovered statement items."""
    templ_path = COV_STMT_TEMPL_PATH
    try:
        src_lines = my_io.read_lines(src_file_path, header=False)
        templ = my_io.read_txt(templ_path, header=False)
    except (RuntimeError, ValueError) as e:
        msg = f"Missing src file {src_file_path} or template {templ_path}"
        logger.exception(None, msg)
        raise RuntimeError(msg) from e
    ast_map = my_ast.uncov_map(src_file_path, uncovered_lines)
    items: list[str] = []
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

        formatted_stmt = templ.format(
            context_snippet=context_snippet,
            function_name=func_name,
            audit_msg=audit_msg,
        )
        items.append(formatted_stmt)
    return "\n\n".join(items) if items else ""


def _fmt_branches(
    src_file_path: Path | str,
    branch_notes: list[tuple[int, str]],
) -> str:
    """Pen branch jump template items with AST context."""
    templ_path = COV_BRANCH_TEMPL_PATH
    try:
        src_lines = my_io.read_lines(src_file_path, header=False)
        templ = my_io.read_txt(templ_path, header=False)
    except (RuntimeError, ValueError) as e:
        msg = f"Missing src file {src_file_path} or template {templ_path}"
        logger.exception(None, msg)
        raise RuntimeError(msg) from e

    ast_map = my_ast.uncov_map(src_file_path, [ln for ln, _ in branch_notes])
    items: list[str] = []
    for line_num, audit in branch_notes:
        start_idx = max(0, line_num - SNIPPET_CONTEXT_OFFSET)
        end_idx = min(len(src_lines), line_num + SNIPPET_END_OFFSET)
        branch_snippet = "\n".join(src_lines[start_idx:end_idx]) if src_lines else audit

        func_name, _ = ast_map.get(
            line_num,
            ("conditional block", "Partial branch coverage."),
        )
        descriptive_audit = _parse_branch_audit(audit)

        formatted_branch = templ.format(
            branch_snippet=branch_snippet,
            function_name=func_name,
            audit=descriptive_audit,
        )
        items.append(formatted_branch)
    return "\n\n".join(items) if items else ""


def run(src_file_path: Path | str, run_output: RunOutput) -> RunOutput:
    """Scan pytest cov annotation file and build tips to address cov gaps.

    Fill template from config/templates/cov_tips.md with cov info from annotations.
    """
    func = f"{__name__}"
    logger.start(func, target=src_file_path)

    uncovered_lines, branch_notes, cov_status, status = issues(src_file_path)
    if status == RunState.PASS:
        return replace(run_output, status=RunState.PASS)
    if cov_status == CovState.MISSING:
        return replace(run_output, status=RunState.FAIL, brief=BRIEF_MISSING)

    stmt_brief = _fmt_stmts(src_file_path, uncovered_lines)
    branch_brief = _fmt_branches(src_file_path, branch_notes)
    brief = f"{stmt_brief}\n\n{branch_brief}"

    logger.end(func, target=src_file_path)
    return replace(
        run_output,
        brief=brief,
        status=RunState.FAIL,
    )
