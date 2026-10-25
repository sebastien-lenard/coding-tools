# src/coding_tools/batch_unit_test_ask_llm.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Run batch or single unit test writing jointly with caps on parallel runs."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from coding_tools.logger import get_project_logger, setup_logging
from coding_tools.unit_test_orchestrator import execute_workflow

logger = get_project_logger(__name__)


def get_test_file_path(source_file: str | Path) -> str:
    """Get unit test path matching source path under tests/unit.

    Strips src prefix if present, adds tests/unit.
    """
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
    """Create test file and parent dirs if missing with min header stub.

    Writes UTF-8 text with SPDX headers if file is absent or empty.
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
        logger.progress(test_file, "Created test file")


async def run_workflow_with_iterations(
    test_file: str,
    source_file: str,
    max_iterations: int = 5,
    semaphore: asyncio.Semaphore | None = None,
) -> dict[str, Any]:
    """Run execute_workflow loop up to max iterations with parallel run limit.

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
                allow_gemini = iteration < max_iterations

                logger.progress(
                    prefix,
                    f"Start step {iteration}/{max_iterations}"
                    f" using llm call: {allow_gemini}",
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
                if not allow_gemini:
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
    headers = ["Test File", "Stage", "Status", "Steps"]
    rows = [
        [res["test_file"], res["stage"], res["status"], str(res["iterations"])]
        for res in results
    ]
    logger.summary_table(title, headers, rows)


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
            test_file = get_test_file_path(source_file)
            ensure_test_file_exists(test_file)
            targets.append((test_file, source_file))
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
            test_file = get_test_file_path(source_file)
            ensure_test_file_exists(test_file)
            targets.append((test_file, source_file))
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
    logger.progress(None, f"End {func}")


def main() -> None:
    """Run async_main in event loop."""
    setup_logging()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
