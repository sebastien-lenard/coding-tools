# src/coding_tools/docstring.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pen and check docstrings using a LLM.

AST check of unexpected edits of code. Parallel runs with cap.
Writes files.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from coding_tools import (
    file_handler,
    llm_router,
    my_ast,
    my_io,
    my_logger,
    workspace_stamper,
)
from coding_tools.llm_protocol import LLMResponse, StructuredGenerationOptions
from coding_tools.my_logger import RunState

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol

PARALLEL_CALLS = 2
SKILL_PATH = Path("config/skills/docstring.md")
TEMPLATE_PATH = Path("config/templates/improve.md")
STEPS = 2
SUMMARY_HEADERS = ("File", "Status")

logger = my_logger.logger(__name__)


@dataclass
class Context:
    """Run context."""

    skill: str
    template: str
    file_paths: list[Path]
    start_date: str
    semaphore: asyncio.Semaphore
    llm: LLMClientProtocol


@dataclass
class SummaryRow:
    """Run summary per file."""

    file: str
    status: str


def _init(path: Path | str) -> Context:
    file_paths = file_handler.files(path)
    if not file_paths:
        msg = f"No file at {path}"
        raise FileNotFoundError(msg)
    return Context(
        skill=workspace_stamper.strip_header(my_io.read_txt(SKILL_PATH)),
        template=workspace_stamper.strip_header(my_io.read_txt(TEMPLATE_PATH)),
        file_paths=file_paths,
        start_date=datetime.now().astimezone().strftime("%y-%m-%d"),
        semaphore=asyncio.Semaphore(PARALLEL_CALLS),
        llm=llm_router.get_llm_client(),
    )


async def _edit_docstrings(
    file_path: Path,
    ctx: Context,
) -> SummaryRow:
    """Run two passes of docstring enhancement using LLM with AST check.

    Retry up to twice per pass on failure. Return original code on failure.
    """
    try:
        current_code = my_io.read_txt(file_path)
    except (OSError, UnicodeEncodeError):
        logger.exception(None, "")
        return SummaryRow(
            file=file_path.name,
            status="Failed",
        )
    file_stem = file_path.stem
    status = RunState.START
    for step in range(STEPS):
        step_msg = f"{file_stem} {step + 1}/{STEPS}"
        try:
            logger.start(step_msg)
            contents: list[object] = [
                ctx.template.format(skill=ctx.skill, path=file_path, code=current_code),
            ]
            options = StructuredGenerationOptions(
                response_schema=LLMResponse,
                prefix=file_stem,
                spinner_msg=f"Pen docstrings LLM call {step + 1}",
                system_instruction="",
                tool_name="docstring",
                process_step=f"{step}",
                target_file=str(file_path),
                start_date=ctx.start_date,
            )
            response = ctx.llm.response(
                contents,
                options,
            )
            resp_typed = cast("LLMResponse", response)
            candidate_code = resp_typed.code

            if my_ast.match_codes(current_code, candidate_code):
                current_code = candidate_code
                status = RunState.PASS
                my_io.write_txt(candidate_code, file_path)
                logger.end(step_msg, "")
            else:
                logger.warning(step_msg, "Failed")
        except Exception:
            logger.exception(step_msg, "Failed")

    return SummaryRow(
        file=file_path.name,
        status=("Edited" if status == RunState.PASS else "Failed"),
    )


async def _run(
    file_path: Path,
    ctx: Context,
) -> SummaryRow:
    """Run docstring enhancement on .py script using LLM and save file."""
    async with ctx.semaphore:
        return await _edit_docstrings(
            file_path,
            ctx,
        )


async def async_main() -> None:
    """Run async main flow for docstring writer.

    Parse arguments, get target files, cap to 4 parallel runs.
    Exit if target missing or empty.
    """
    func = __name__
    logger.start(func)

    parser = argparse.ArgumentParser(
        description="Pen docstrings using LLMs",
    )
    parser.add_argument(
        "path",
        type=str,
        help="Target Python file or directory (needed).",
    )
    args = parser.parse_args()

    try:
        ctx = _init(path=args.path)
    except (OSError, UnicodeEncodeError) as e:
        logger.exception(None, "")
        logger.end(func)
        raise SystemExit(1) from e

    tasks = [_run(f, ctx) for f in ctx.file_paths]
    summary_rows = await asyncio.gather(*tasks)

    logger.summary_table(
        "Docstring Summary",
        list(SUMMARY_HEADERS),
        [[row.file, row.status] for row in summary_rows],
    )
    logger.end(func)


def main() -> None:
    """Run async main loop via asyncio.run."""
    my_logger.setup()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
