# src/coding_tools/pytest_cov.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Scan pytest cov files, get bad lines, build tips for LLM.

Reads cov report, finds gaps, fills templates.
"""

from __future__ import annotations

import re
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import cast

from coding_tools import my_ast, my_io, my_logger, my_path
from coding_tools.my_run import RunOutput, RunState

logger = my_logger.logger(__name__)


class CovState(Enum):
    """Give unit test cov state for source.

    Full, part, or none.
    """

    FULL = "Fully covered"
    PARTLY = "Partly covered"
    MISSING = "No coverage"


BRIEF_MISSING = "No unit test seems to cover the source file"
MAX_TEMPLATE_PARTS = 3
MAX_SUBTEMPLATE_PARTS = 2
COV_STMT_TEMPL_PATH = Path("conf/templates/cov_stmt.md")
COV_BRANCH_TEMPL_PATH = Path("conf/templates/cov_branch.md")
SNIPPET_CONTEXT_OFFSET = 3
SNIPPET_END_OFFSET = 2


def _read(path: Path, err_msg: str, *, lines: bool = True) -> list[str] | str:
    """Read file lines, raising RuntimeError on failure."""
    try:
        return (
            my_io.read_lines(path, header=False)
            if lines
            else my_io.read_txt(path, header=False)
        )
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        logger.exception(None, err_msg)
        raise RuntimeError(err_msg) from e


def _pytest_uncov_branch_notes(
    src_file_path: Path | str,
) -> list[tuple[int, int, str]]:
    """Extract branch pairs like 52->54 from pytest log output."""
    branch_notes = []
    try:
        pytest_log_path = my_path.get_pytest_log_path(src_file_path)
        log_content = my_io.read_txt(pytest_log_path, header=False, raise_err=False)
    except (FileNotFoundError, RuntimeError, ValueError):
        return []

    for line in log_content.splitlines():
        if Path(src_file_path).name in line or "Stmts" in line:
            parts = line.split()
            for part in parts:
                if "->" in part:
                    for item in part.split(","):
                        if "->" in item:
                            try:
                                start_str, end_str = item.strip().split("->")
                                branch_notes.append(
                                    (int(start_str), int(end_str), item.strip()),
                                )
                            except ValueError:
                                continue
    return branch_notes


def issues(
    src_file_path: Path | str,
) -> tuple[list[int], list[tuple[int, int, str]], CovState, RunState]:
    """Scan cov file, get bad lines and branch notes.

    Reads pytest cov output. Returns uncov lines, branch notes, cov
    state, and run state. Catch FileNotFoundError, RuntimeError,
    ValueError. Yields fail if gaps found.
    """
    uncov_lines: list[int] = []
    branch_notes = _pytest_uncov_branch_notes(src_file_path)

    try:
        cov_path = my_path.pytest_cov_path(src_file_path)
    except RuntimeError as e:
        logger.warning(None, str(e))
        return uncov_lines, branch_notes, CovState.MISSING, RunState.FAIL
    try:
        ann_lines = _read(
            cov_path,
            (
                f"No cov file (or corrupted) for {src_file_path} in "
                f"{my_path.pytest_cov_dir(src_file_path)}"
            ),
        )
    except RuntimeError as e:
        logger.warning(None, str(e))
        return uncov_lines, branch_notes, CovState.MISSING, RunState.FAIL

    for idx, line in enumerate(ann_lines):
        line_num = idx + 1
        if line.startswith("!"):
            uncov_lines.append(line_num)

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
    """Turn raw branch line into audit text.

    Checks for no branch or exit jumps. Returns formatted audit string.
    """
    match = re.search(r"(\d+)->(exit|\d+)", audit_line)
    if match:
        target = match.group(2)
        if target == "exit":
            return "Branch jump exited early; the other branch path was never taken."
        return f"Branch jump to line {target} was never taken; tests only ran one way."

    return f"Partial branch test coverage jump: {audit_line}"


def _fmt_stmts(src_file_path: Path, uncovered_lines: list[int]) -> str:
    """Format uncov statement items with templates.

    Reads src file and template. Calls my_ast to map uncov lines. Returns joined items.
    """
    templ_path = COV_STMT_TEMPL_PATH
    src_lines = _read(
        Path(src_file_path),
        f"Missing src file {src_file_path}",
        lines=True,
    )
    templ = cast(
        "str",
        _read(templ_path, f"Missing template {templ_path}", lines=False),
    )

    ast_map = my_ast.uncov_map(src_file_path, uncovered_lines)
    items: list[str] = []
    for line_num in uncovered_lines:
        if line_num > len(src_lines):
            continue

        stmt_snippet = src_lines[line_num - 1]

        start_idx = max(0, line_num - SNIPPET_CONTEXT_OFFSET)
        end_idx = min(len(src_lines), line_num + SNIPPET_END_OFFSET)
        snippet_lines = src_lines[start_idx:end_idx]
        context_snippet = "\n".join(snippet_lines)

        func_name, audit_msg = ast_map.get(
            line_num,
            ("module scope", "Uncovered source statement."),
        )

        formatted_stmt = templ.format(
            stmt_snippet=stmt_snippet,
            context_snippet=context_snippet,
            function_name=func_name,
            audit_msg=audit_msg,
        )
        items.append(formatted_stmt)
    return "\n\n".join(items) if items else ""


def _fmt_branches(
    src_file_path: Path,
    branch_notes: list[tuple[int, int, str]],
) -> str:
    """Format branch jump items with AST context.

    Reads src file and branch template. Maps notes and builds text. Returns items.
    """
    templ_path = COV_BRANCH_TEMPL_PATH
    src_lines = _read(
        Path(src_file_path),
        f"Missing src file {src_file_path}",
        lines=True,
    )
    templ = cast(
        "str",
        _read(templ_path, f"Missing template {templ_path}", lines=False),
    )

    ast_map = my_ast.uncov_map(
        src_file_path,
        [start_ln for start_ln, _, _ in branch_notes],
    )
    items: list[str] = []
    for start_line, target_line, audit in branch_notes:
        if start_line > len(src_lines) or (
            target_line > 0 and target_line > len(src_lines)
        ):
            continue

        branch_snippet = src_lines[start_line - 1] if start_line > 0 else audit
        stmt_snippet = (
            src_lines[target_line - 1]
            if target_line > 0 and target_line <= len(src_lines)
            else branch_snippet
        )

        start_idx = max(0, start_line - SNIPPET_CONTEXT_OFFSET)
        end_idx = min(len(src_lines), start_line + SNIPPET_END_OFFSET)
        context_snippet = (
            "\n".join(src_lines[start_idx:end_idx]) if src_lines else audit
        )

        branch_cxt_idx = (
            max(0, target_line - SNIPPET_CONTEXT_OFFSET) if target_line > 0 else 0
        )
        branch_cxt_end = (
            min(len(src_lines), target_line + SNIPPET_END_OFFSET)
            if target_line > 0
            else 0
        )
        branch_cxt_snippet = (
            "\n".join(src_lines[branch_cxt_idx:branch_cxt_end])
            if target_line > 0 and target_line <= len(src_lines)
            else branch_snippet
        )

        func_name, _ = ast_map.get(
            start_line,
            ("conditional block", "Partial branch coverage."),
        )
        descriptive_audit = _parse_branch_audit(audit)

        formatted_branch = templ.format(
            stmt_snippet=stmt_snippet,
            branch_snippet=branch_snippet,
            context_snippet=context_snippet,
            branch_cxt_snippet=branch_cxt_snippet,
            function_name=func_name,
            audit=descriptive_audit,
        )
        items.append(formatted_branch)
    return "\n\n".join(items) if items else ""


def run(src_file_path: Path | str, run_output: RunOutput) -> RunOutput:
    """Scan pytest cov file and build tips for gaps.

    Gets issues, formats statements and branches, updates run output. Returns RunOutput.
    """
    func = f"{__name__}"
    logger.start(func, target=src_file_path)

    uncovered_lines, branch_notes, cov_status, status = issues(src_file_path)
    if status == RunState.PASS:
        return replace(run_output, status=RunState.PASS)
    if cov_status == CovState.MISSING:
        return replace(run_output, status=RunState.FAIL, brief=BRIEF_MISSING)

    stmt_brief = _fmt_stmts(Path(src_file_path), uncovered_lines)
    branch_brief = _fmt_branches(Path(src_file_path), branch_notes)

    brief_parts = [p for p in [stmt_brief, branch_brief] if p]
    brief = "\n\n".join(brief_parts)

    logger.end(func, target=src_file_path)
    return replace(
        run_output,
        brief=brief,
        status=RunState.FAIL,
    )
