# src/coding_tools/batch_unit_test_ask_llm.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Run batch or single unit test writing jointly with caps on parallel runs."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from coding_tools import file_handler, my_logger
from coding_tools.unit_test_orchestrator import execute_workflow

logger = my_logger.logger(__name__)


async def pen_unit_test(
    test_file: str,
    source_file: str,
    max_iterations: int = 5,
    semaphore: asyncio.Semaphore | None = None,
) -> dict[str, Any]:
    """Pen and check unit tests through a loop up to max steps with parallel run cap.

    No call to LLM on final step. Ends on success or when llm not able to fix issues.
    """
    prefix = Path(test_file).name

    async def task() -> dict[str, Any]:
        final_stage = "Pytest/Coverage"
        final_status = "Failed"
        iterations_run = 0

        try:
            for iteration in range(1, max_iterations + 1):
                iterations_run = iteration
                call_llm = iteration < max_iterations

                logger.progress(
                    prefix,
                    f"Start step {iteration}/{max_iterations}"
                    f" using llm call: {call_llm}",
                )

                # Run the synchronous workflow in a thread pool executor
                success, stage, status = await asyncio.to_thread(
                    execute_workflow,
                    test_file,
                    source_file,
                    allow_llm=call_llm,
                )

                final_stage = stage
                final_status = status

                if success:
                    logger.progress(
                        prefix,
                        f"Done step {iteration}",
                    )
                    final_stage = "All Stages"
                    final_status = "Success"
                    break

                if status == "No LLM fix":
                    logger.error(
                        prefix,
                        "Failed. LLM not able to fix issues",
                    )
                    break

                if status == "Fixed":
                    logger.progress(
                        prefix,
                        f"Applied fix by step {iteration}",
                    )
                    continue

                logger.warning(
                    prefix,
                    f"End step {iteration}. Stage: {final_stage}. "
                    f"Status: {final_status}",
                )
                if not call_llm:
                    break

        except Exception:
            logger.exception(
                prefix,
                "Failed run_workflow_with_iterations()",
            )
            final_status = "Error"

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
    """Log formatted summary table of results for test files."""
    title = (
        "Unit test writing (batch) Summary:"
        if processed_multiple
        else "Unit test writing (file) Summary"
    )
    headers = {
        "test_file": "Test File",
        "stage": "Stage",
        "status": "Status",
        "iterations": "Steps",
    }

    logger.summary_table(title, headers, results)


async def async_main() -> None:
    """Parse args, collect source files, and run tasks jointly.

    Caps parallel runs to 2 via semaphore. Skips __init__.py.
    """
    func = f"{__name__}"
    parser = argparse.ArgumentParser(
        description="Pen unit tests",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="src",
        help="Path to source file or dir (default: src)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Max number of steps per file (default: 5)",
    )
    args = parser.parse_args()

    target_path = Path(args.target)
    targets: list[tuple[str, str]] = []

    if target_path.is_file():
        if target_path.suffix == ".py":
            source_file = str(target_path)
            test_file = file_handler.unit_test_path(source_file)
            targets.append((str(test_file), source_file))
        else:
            logger.error(None, "Bad file extension (Needed .py)")
            return
    elif target_path.is_dir():
        src_dir = target_path / "src" if (target_path / "src").is_dir() else target_path
        py_files = sorted(src_dir.glob("**/*.py"))
        for py_file in py_files:
            if py_file.name == "__init__.py":
                continue
            source_file = str(py_file)
            test_file = file_handler.unit_test_path(source_file)
            targets.append((str(test_file), source_file))
    else:
        logger.error(None, f"Missing target file or dir {target_path}")
        return

    processed_multiple = len(targets) > 1
    max_iterations = args.max_iterations

    logger.progress(
        None,
        f"Start {func}. Max steps: {max_iterations}. Targets: {len(targets)}",
    )
    for test_f, src_f in targets:
        logger.progress(None, f"Test: {test_f}. Src: {src_f}")

    semaphore = asyncio.Semaphore(2)
    results = await asyncio.gather(
        *[
            pen_unit_test(
                test_file,
                source_file,
                max_iterations=max_iterations,
                semaphore=semaphore,
            )
            for test_file, source_file in targets
        ],
    )

    print_summary_table(list(results), processed_multiple=processed_multiple)
    logger.progress(None, f"End {func}")


def main() -> None:
    """Run async_main in event loop."""
    my_logger.setup()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
