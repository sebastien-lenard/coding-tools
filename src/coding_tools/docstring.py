# src/coding_tools/docstring.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pen and check docstrings using a LLM.

AST check of unexpected edits of code. Parallel runs with cap.
Writes files, stamps workspace.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from coding_tools import my_logger
from coding_tools.llm_prompts import load_skill
from coding_tools.llm_protocol import LLMResponse, StructuredGenerationOptions
from coding_tools.llm_router import get_llm_client
from coding_tools.workspace_stamper import TargetWorkspace, WorkspaceStamper

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol

logger = my_logger.logger("coding_tools.docstring_enhancer")

MAX_DOCSTRING_LINES = 10


def _del_docstrings(tree: ast.AST) -> None:
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


def _check_code(
    original_code: str,
    new_code: str,
    prefix: str,
) -> tuple[bool, str]:
    """Scan AST changes to ensure only docstrings changed.

    False if syntax error, line count exceed max, or non-docstring code changed.
    """
    logger.progress(prefix, "Check AST edits")
    try:
        orig_tree = ast.parse(original_code)
        new_tree = ast.parse(new_code)
    except SyntaxError as e:
        msg = "Bad code syntax (failed scan)"
        logger.exception(prefix, msg)
        return False, f"{msg}: {e}"

    for node in ast.walk(new_tree):
        if isinstance(
            node,
            (ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module),
        ) and (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            doc_lines = node.body[0].value.value.splitlines()
            total_lines = len(doc_lines)
            if total_lines > MAX_DOCSTRING_LINES:
                msg = f"Docstring lines: {total_lines} (over max {MAX_DOCSTRING_LINES})"
                logger.warning(prefix, msg)
                return (False, msg)

    _del_docstrings(orig_tree)
    _del_docstrings(new_tree)

    orig_normalized = ast.unparse(orig_tree)
    new_normalized = ast.unparse(new_tree)

    if orig_normalized != new_normalized:
        msg = "Spotted code edits"
        logger.warning(prefix, msg)
        return (False, msg)

    logger.progress(prefix, "Done AST check")
    return True, "OK"


async def _edit_docstrings(
    client: LLMClientProtocol,
    contents: list[object],
    options: StructuredGenerationOptions,
    original_code: str,
    prefix: str,
) -> tuple[bool, str]:
    """Edit docstring in code calling LLM and check response against Pydantic schema.

    Retry up to twice on failure. Return original code on failure.
    """
    func = "_edit_docstrings()"
    max_step = 2
    for attempt in range(max_step):
        try:
            logger.progress(
                prefix,
                f"Start step {attempt + 1}/{max_step} of {func}",
            )
            response = client.generate_structured_response(
                contents,
                options,
            )
            resp_typed = cast("LLMResponse", response)
            candidate_code = resp_typed.code

            valid, reason = _check_code(
                original_code,
                candidate_code,
                prefix,
            )
            if valid:
                logger.progress(
                    prefix,
                    f"End step {attempt + 1}/{max_step} of {func}",
                )
                return True, candidate_code
            logger.warning(
                prefix,
                f"Failed check: {reason}",
            )
            contents.append(
                (f"Previous try failed: {reason}. Fix"),
            )
        except Exception:
            logger.exception(
                prefix,
                "Failed run of {func}",
            )
    return False, original_code


async def process_file_workflow(
    file_path: Path,
    semaphore: asyncio.Semaphore,
    start_date: str,
) -> dict[str, Any]:
    """Run two-step docstring penning/editing on .py script using LLM.

    Pens neater docstrings, stamps workspace, and returns execution dict status.
    """
    async with semaphore:
        prefix = file_path.stem
        logger.progress(prefix, f"Start process_file_workflow() for {file_path}")

        client = get_llm_client()
        original_code = file_path.read_text(encoding="utf-8")
        current_code = original_code

        skill_content = load_skill("docstring_enhancer.md")

        enhancement_contents: list[object] = [
            f"--- Target File: {file_path} ---\n{current_code}",
            "Follow instructions on docstrings.",
        ]
        options_pass1 = StructuredGenerationOptions(
            response_schema=LLMResponse,
            prefix=prefix,
            spinner_msg="Pen docstrings",
            system_instruction=skill_content,
            tool_name="docstring-enhancer",
            process_step="pass-1",
            target_file=str(file_path),
            start_date=start_date,
        )

        success, candidate = await _edit_docstrings(
            client,
            enhancement_contents,
            options_pass1,
            original_code,
            prefix,
        )
        if not success:
            logger.error(prefix, "Failed step 1 failed after retry limit")
            return {
                "file": str(file_path),
                "status": "Failed",
                "stage": "Step 1: Enhancement",
            }
        current_code = candidate

        verification_contents: list[object] = [
            f"--- Target File: {file_path} ---\n{current_code}",
            "Follow instructions on docstrings.",
        ]
        options_pass2 = StructuredGenerationOptions(
            response_schema=LLMResponse,
            prefix=prefix,
            spinner_msg="Verifying docstrings...",
            system_instruction=skill_content,
            tool_name="docstring-enhancer",
            process_step="pass-2",
            target_file=str(file_path),
            start_date=start_date,
        )

        success_pass2, candidate_v2 = await _edit_docstrings(
            client,
            verification_contents,
            options_pass2,
            original_code,
            prefix,
        )
        if success_pass2:
            current_code = candidate_v2
        else:
            logger.warning(
                prefix,
                "Pass 2 verification failed, falling back.",
            )

        file_path.write_text(current_code, encoding="utf-8")
        logger.progress(prefix, f"Saved enhanced code to {file_path}", full_path=True)

        try:
            workspace = TargetWorkspace(
                project_dir=Path.cwd(),
                target_path=file_path.resolve(),
                run_path_stamp=True,
                run_license_stamp=True,
                extracted_license_id="Apache-2.0",
            )
            stamper = WorkspaceStamper(workspace=workspace)
            stamper.run()
        except Exception:
            logger.exception(
                prefix,
                "Workspace stamper issue during save",
            )

        logger.progress(prefix, f"Done docstring for {file_path}")
        return {
            "file": str(file_path),
            "status": "SUCCESS",
            "stage": "Completed",
        }


def _summary(results: list[dict[str, Any]], project_root: Path) -> None:
    """Log summary table of edited files and statuses.

    Yield relative paths from project root.
    """
    headers = ["File", "Status", "Stage"]
    rows = []
    for res in results:
        file_path_obj = Path(res["file"])
        try:
            display_path = file_path_obj.relative_to(project_root).as_posix()
        except ValueError:
            display_path = str(file_path_obj)
        rows.append([display_path, res["status"], res["stage"]])

    logger.summary_table("Docstring Summary", headers, rows)


async def async_main() -> None:
    """Run async main flow for docstring writer.

    Parse arguments, get target files, cap to 4 parallel runs.
    Exit if target missing or empty.
    """
    start_date = datetime.now().astimezone().strftime("%y-%m-%d")
    logger.progress(None, "Start docstring write")

    parser = argparse.ArgumentParser(
        description="Pen docstrings using LLMs",
    )
    parser.add_argument(
        "target",
        type=str,
        help="Target Python file or directory (needed).",
    )
    args = parser.parse_args()

    project_root = Path.cwd().resolve()
    target_path = Path(args.target).resolve()
    if not target_path.exists():
        logger.error(None, f"Target path doesn't exist: {target_path}")
        raise SystemExit(1)

    targets: list[Path] = []
    if target_path.is_file() and target_path.suffix == ".py":
        targets.append(target_path)
    elif target_path.is_dir():
        targets.extend(sorted(target_path.rglob("*.py")))

    if not targets:
        logger.error(None, f"No .py files at: {target_path}")
        raise SystemExit(1)

    logger.progress(
        None,
        f"Got {len(targets)} .py files",
    )
    semaphore = asyncio.Semaphore(4)
    tasks = [process_file_workflow(f, semaphore, start_date) for f in targets]
    results = await asyncio.gather(*tasks)

    _summary(list(results), project_root)
    logger.progress(None, "Done docstring pen")


def main() -> None:
    """Run async main workflow loop via asyncio.run."""
    asyncio.run(async_main())
