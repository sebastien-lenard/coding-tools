# src/coding_tools/docstring_enhancer.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Automate docstring enhancement via LLM API.

Stamps workspace and validates AST mutations.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from coding_tools.llm_prompts import load_skill
from coding_tools.llm_protocol import LLMResponse, StructuredGenerationOptions
from coding_tools.llm_router import get_llm_client
from coding_tools.workspace_stamper import TargetWorkspace, WorkspaceStamper

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("coding_tools.docstring_enhancer")

MAX_DOCSTRING_LINES = 5


def _strip_docstrings(tree: ast.AST) -> None:
    """Remove docstrings from AST tree nodes in place."""
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


def validate_docstring_mutations(
    original_code: str,
    new_code: str,
    prefix: str,
) -> tuple[bool, str]:
    """Check AST validity and ensure non-docstring code unchanged.

    Fail if docstring exceeds max lines or code mutates.
    """
    logger.info("[%s] Validating AST transformations...", prefix)
    try:
        orig_tree = ast.parse(original_code)
        new_tree = ast.parse(new_code)
    except SyntaxError as e:
        logger.exception("[%s] SyntaxError in modified code", prefix)
        return False, f"SyntaxError in modified code: {e}"

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
                logger.warning(
                    "[%s] Docstring line count %d exceeds maximum %d lines.",
                    prefix,
                    total_lines,
                    MAX_DOCSTRING_LINES,
                )
                return (
                    False,
                    (
                        f"Docstring exceeds max {MAX_DOCSTRING_LINES}"
                        f" lines (found {total_lines})."
                    ),
                )

    _strip_docstrings(orig_tree)
    _strip_docstrings(new_tree)

    orig_normalized = ast.unparse(orig_tree)
    new_normalized = ast.unparse(new_tree)

    if orig_normalized != new_normalized:
        logger.warning(
            "[%s] Non-docstring structures mutation detected.",
            prefix,
        )
        return (
            False,
            "Non-docstring code structures were modified.",
        )

    logger.info("[%s] AST validation passed.", prefix)
    return True, "Valid"


async def _run_enhancement_pass(
    client: LLMClientProtocol,
    contents: list[object],
    options: StructuredGenerationOptions,
    original_code: str,
    prefix: str,
) -> tuple[bool, str]:
    """Call LLM API to enhance docstrings with retry logic.

    Yield candidate code if validation passes. Two attempts max.
    """
    for attempt in range(2):
        try:
            logger.info(
                "[%s] Executing pass (Attempt %d/2)...",
                prefix,
                attempt + 1,
            )
            response = client.generate_structured_response(
                contents,
                options,
            )
            resp_typed = cast("LLMResponse", response)
            candidate_code = resp_typed.code

            valid, reason = validate_docstring_mutations(
                original_code,
                candidate_code,
                prefix,
            )
            if valid:
                logger.info("[%s] Pass validated successfully.", prefix)
                return True, candidate_code
            logger.warning(
                "[%s] Validation failed: %s. Retrying...",
                prefix,
                reason,
            )
            contents.append(
                (f"Previous attempt validation failed: {reason}. Fix and try again."),
            )
        except Exception:
            logger.exception(
                "[%s] Pass execution encountered exception",
                prefix,
            )
    return False, original_code


async def process_file_workflow(
    file_path: Path,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Run two-pass docstring workflow on file.

    Save enhanced code, stamp workspace, return status.
    """
    async with semaphore:
        prefix = file_path.stem
        logger.info(
            "[%s] Starting docstring workflow for %s",
            prefix,
            file_path,
        )

        client = get_llm_client()
        original_code = file_path.read_text(encoding="utf-8")
        current_code = original_code

        skill_content = load_skill("docstring_enhancer.md")

        enhancement_contents: list[object] = [
            f"--- Target File: {file_path} ---\n{current_code}",
            "Please enhance and correct docstrings according to guidelines.",
        ]
        options_pass1 = StructuredGenerationOptions(
            response_schema=LLMResponse,
            prefix=prefix,
            spinner_msg="Enhancing docstrings...",
            system_instruction=skill_content,
        )

        success, candidate = await _run_enhancement_pass(
            client,
            enhancement_contents,
            options_pass1,
            original_code,
            prefix,
        )
        if not success:
            logger.error("[%s] Pass 1 failed after retry limit.", prefix)
            return {
                "file": str(file_path),
                "status": "FAILED",
                "stage": "Pass 1: Enhancement",
            }
        current_code = candidate

        verification_contents: list[object] = [
            f"--- Target File: {file_path} ---\n{current_code}",
            (
                "Review enhanced docstrings. Ensure edge cases and "
                "subtleties are captured, max 5 lines respected."
            ),
        ]
        options_pass2 = StructuredGenerationOptions(
            response_schema=LLMResponse,
            prefix=prefix,
            spinner_msg="Verifying docstrings...",
            system_instruction=skill_content,
        )

        success_pass2, candidate_v2 = await _run_enhancement_pass(
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
                "[%s] Pass 2 verification failed, falling back.",
                prefix,
            )

        file_path.write_text(current_code, encoding="utf-8")
        logger.info("[%s] Saved enhanced code to %s", prefix, file_path)

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
                "[%s] Workspace stamper issue during save",
                prefix,
            )

        logger.info(
            "[%s] Ended docstring workflow for %s",
            prefix,
            file_path,
        )
        return {
            "file": str(file_path),
            "status": "SUCCESS",
            "stage": "Completed",
        }


def print_summary_table(results: list[dict[str, Any]], project_root: Path) -> None:
    """Log summary table of processed files and statuses."""
    logger.info("==================================================")
    logger.info("DOCSTRING ENHANCER EXECUTION SUMMARY TABLE")
    logger.info("==================================================")
    logger.info("%-45s | %-10s | %-15s", "File", "Status", "Stage")
    logger.info("-" * 76)
    for res in results:
        file_path_obj = Path(res["file"])
        try:
            display_path = file_path_obj.relative_to(project_root).as_posix()
        except ValueError:
            display_path = str(file_path_obj)
        logger.info(
            "%-45s | %-10s | %-15s",
            display_path,
            res["status"],
            res["stage"],
        )
    logger.info("==================================================")


async def async_main() -> None:
    """Parse args, collect target files, run concurrent workflows.

    Use semaphore limit 4.
    """
    logger.info("[INFO] Initializing docstring_enhancer workflow...")
    parser = argparse.ArgumentParser(
        description="Automated Python docstring enhancer and corrector via Gemini LLM.",
    )
    parser.add_argument(
        "target",
        type=str,
        help="Target Python source file or directory (mandatory).",
    )
    args = parser.parse_args()

    project_root = Path.cwd().resolve()
    target_path = Path(args.target).resolve()
    if not target_path.exists():
        logger.error("[ERROR] Target path does not exist: %s", target_path)
        raise SystemExit(1)

    targets: list[Path] = []
    if target_path.is_file() and target_path.suffix == ".py":
        targets.append(target_path)
    elif target_path.is_dir():
        targets.extend(sorted(target_path.rglob("*.py")))

    if not targets:
        logger.error(
            "[ERROR] No Python source files found at target: %s",
            target_path,
        )
        raise SystemExit(1)

    logger.info(
        "[INFO] Collected %d target source files for enhancement.",
        len(targets),
    )
    semaphore = asyncio.Semaphore(4)
    tasks = [process_file_workflow(f, semaphore) for f in targets]
    results = await asyncio.gather(*tasks)

    print_summary_table(list(results), project_root)
    logger.info("[INFO] docstring_enhancer workflow finished.")


def main() -> None:
    """Run async main workflow loop."""
    asyncio.run(async_main())
