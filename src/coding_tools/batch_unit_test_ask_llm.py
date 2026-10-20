# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Run automated test generation, type checking, and linting concurrently.

Processed for multiple files with 5 iterations max.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

from coding_tools.unit_test_orchestrator import execute_workflow

# Configure logging format and level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_test_file_path(source_file: str | Path) -> str:
    """Automatically detect the unit test file path from a source file path."""
    path = Path(source_file)
    parts = path.parts
    if "src" in parts:
        idx = parts.index("src")
        rel_parts = parts[idx + 1 :]
    else:
        rel_parts = (
            path.relative_to(path.anchor).parts[1:]
            if len(path.parts) > 1
            else path.parts
        )

    if len(rel_parts) > 1:
        sub_path = Path(*rel_parts[1:-1]) / f"test_{rel_parts[-1]}"
    else:
        sub_path = f"test_{path.name}"

    return str(Path("tests/unit") / sub_path)


def ensure_test_file_exists(test_file: str) -> None:
    """Ensure the test file and its parent directories exist.

    If the file does not exist, create it with a minimal valid test stub
    to prevent empty-file parser failures.
    """
    test_path = Path(test_file)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    if not test_path.exists() or test_path.stat().st_size == 0:
        header = (
            f"# SPDX-FileCopyrightText: 2026 Sebastien Lenard "
            f"<sebastien.lenard@gmail.com> and Contributors\n"
            f"# SPDX-License-Identifier: Apache-2.0\n\n"
            f'"""Unit tests for {test_path.name}."""\n\n'
            f"from __init__ import *\n\n"
        )
        test_path.write_text(header, encoding="utf-8")
        logger.info("Initialized missing or empty test file: %s", test_file)


async def run_workflow_with_iterations(
    test_file: str,
    source_file: str,
    max_iterations: int = 5,
    semaphore: asyncio.Semaphore | None = None,
) -> dict[str, Any]:
    """Run a single test file's workflow in a loop up to max_iterations."""

    async def task() -> dict[str, Any]:
        final_stage = "Pytest/Coverage"
        final_status = "FAILED"
        iterations_run = 0

        try:
            for iteration in range(1, max_iterations + 1):
                iterations_run = iteration
                allow_gemini = iteration < max_iterations

                logger.info(
                    "[%s] Starting iteration %d/%d (Gemini allowed: %s)",
                    test_file,
                    iteration,
                    max_iterations,
                    allow_gemini,
                )

                # Run the synchronous workflow in a thread pool executor
                success, stage, status = await asyncio.to_thread(
                    execute_workflow,
                    test_file,
                    source_file,
                    allow_llm=allow_gemini,
                )

                final_stage = stage
                final_status = status

                if success:
                    logger.info(
                        "[%s] All checks passed successfully on iteration %d!",
                        test_file,
                        iteration,
                    )
                    final_stage = "All Stages"
                    final_status = "SUCCESS"
                    break

                if status == "No solution":
                    logger.error(
                        "[%s] Encountered fatal stagnation ('No solution'). "
                        "Stopping iterations early.",
                        test_file,
                    )
                    break

                if status == "FIXED":
                    logger.info(
                        "[%s] Iteration %d applied a fix. Proceeding to next "
                        "iteration to verify...",
                        test_file,
                        iteration,
                    )
                    continue

                logger.warning(
                    "[%s] Iteration %d finished - Stage: %s | Status: %s",
                    test_file,
                    iteration,
                    final_stage,
                    final_status,
                )
                if not allow_gemini:
                    break

        except Exception:
            logger.exception(
                "Workflow encountered an unhandled exception for: %s",
                test_file,
            )
            final_status = "ERROR"

        return {
            "test_file": test_file,
            "stage": final_stage,
            "status": final_status,
            "iterations": iterations_run,
        }

    if semaphore:
        async with semaphore:
            return await task()
    return await task()


def print_summary_table(
    results: list[dict[str, Any]],
    *,
    processed_multiple: bool,
) -> None:
    """Print a clean synthetic summary table of all processed test files."""
    title = (
        "BATCH WORKFLOW EXECUTION SUMMARY"
        if processed_multiple
        else "SINGLE FILE WORKFLOW EXECUTION SUMMARY"
    )
    logger.info(
        "\n===================================================================================",
    )
    logger.info("%s", f"{title:^83}")
    logger.info(
        "===================================================================================",
    )
    logger.info(
        "%s",
        f"{'Test File':<38} | {'Stage':<18} | {'Status':<16} | {'Iters':<5}",
    )
    logger.info(
        "-----------------------------------------------------------------------------------",
    )
    for res in results:
        logger.info(
            "%s",
            f"{res['test_file']:<38} | {res['stage']:<18} | {res['status']:<16} | "
            f"{res['iterations']:<5}",
        )
    logger.info(
        "===================================================================================\n",
    )


async def async_main() -> None:
    """Execute workflows concurrently for multiple files with iteration loops."""
    parser = argparse.ArgumentParser(
        description="Run automated unit test workflow.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="src",
        help="Path to source file or directory (default: src)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum iterations per file (default: 5)",
    )
    args = parser.parse_args()

    target_path = Path(args.target)
    targets: list[tuple[str, str]] = []

    if target_path.is_file():
        if target_path.suffix == ".py":
            source_file = str(target_path)
            test_file = get_test_file_path(source_file)
            ensure_test_file_exists(test_file)
            targets.append((test_file, source_file))
        else:
            logger.error("Target file must be a Python (.py) file.")
            return
    elif target_path.is_dir():
        src_dir = target_path / "src" if (target_path / "src").is_dir() else target_path
        py_files = sorted(src_dir.glob("**/*.py"))
        for py_file in py_files:
            if py_file.name == "__init__.py":
                continue
            source_file = str(py_file)
            test_file = get_test_file_path(source_file)
            ensure_test_file_exists(test_file)
            targets.append((test_file, source_file))
    else:
        logger.error("Target path does not exist: %s", target_path)
        return

    processed_multiple = len(targets) > 1
    max_iterations = args.max_iterations
    logger.info("=" * 65)
    logger.info("STARTING BATCH UNIT TEST WORKFLOW")
    logger.info("Max Iterations per File : %d", max_iterations)
    logger.info("Target Files to Process : %d", len(targets))
    for test_f, src_f in targets:
        logger.info("  - Test: %s | Source: %s", test_f, src_f)
    logger.info("=" * 65)

    semaphore = asyncio.Semaphore(2)

    results = await asyncio.gather(
        *[
            run_workflow_with_iterations(
                test_file,
                source_file,
                max_iterations=max_iterations,
                semaphore=semaphore,
            )
            for test_file, source_file in targets
        ],
    )

    print_summary_table(list(results), processed_multiple=processed_multiple)
    logger.info("Batch concurrent workflow completed successfully.")


def main() -> None:
    """Initiate the asynchronous event loop (Synchronous CLI Gateway)."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
