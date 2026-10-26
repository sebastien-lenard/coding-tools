# src/coding_tools/llm_emcee.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Handle prompt writing, sending to LLM, and check response and write it.

Audit of edits. Parallel runs with cap. File write access.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from coding_tools import (
    file_handler,
    llm_router,
    my_io,
    my_logger,
    workspace_stamper,
)
from coding_tools.llm_protocol import LLMResponse, StructuredGenerationOptions
from coding_tools.my_logger import RunState

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol

PARALLEL_CALLS = 2
TEMPLATE_PATH = Path("config/templates/improve.md")
MAX_STEPS = 2
SUMMARY_HEADERS = ("File", "Status")

logger = my_logger.logger(__name__)


@dataclass
class Context:
    """Run context for updates.

    Holds paths, skills, check func, and semaphore. Needs LLM client.
    """

    func_name: str
    file_paths: list[Path]
    skill: str
    check_func: Callable[[str, str], RunState]
    template: str
    max_steps: int
    start_date: str
    semaphore: asyncio.Semaphore
    llm: LLMClientProtocol


@dataclass
class SummaryRow:
    """Run summary per file.

    Maps file name to status string.
    """

    file: str
    status: str


def init(
    func_name: str,
    path: Path | str,
    skill_path: Path | str,
    check_func: Callable[[str, str], RunState],
    template_path: Path | str = TEMPLATE_PATH,
    max_steps: int = MAX_STEPS,
    parallel_calls: int = PARALLEL_CALLS,
) -> Context:
    """Build and return Context for task.

    Read skill and template files. Raise OSError, UnicodeEncodeError, FileNotFoundError.
    """
    file_paths = file_handler.files(path)
    if not file_paths:
        msg = f"No file at {path}"
        raise FileNotFoundError(msg)
    return Context(
        func_name=func_name,
        file_paths=file_paths,
        skill=workspace_stamper.strip_header(my_io.read_txt(skill_path)),
        check_func=check_func,
        template=workspace_stamper.strip_header(my_io.read_txt(template_path)),
        max_steps=max_steps,
        start_date=datetime.now().astimezone().strftime("%y-%m-%d"),
        semaphore=asyncio.Semaphore(parallel_calls),
        llm=llm_router.get_llm_client(),
    )


async def chat(
    file_path: Path,
    ctx: Context,
) -> SummaryRow:
    """Enhance file content via LLM in steps with checks.

    Read file text. Call LLM API, check result, and write file if pass.
    Return SummaryRow with status.
    """
    try:
        current_txt = my_io.read_txt(file_path)
    except (OSError, UnicodeEncodeError):
        logger.exception(None, "")
        return SummaryRow(
            file=file_path.name,
            status="Failed",
        )
    file_stem = file_path.stem
    status = RunState.START
    for step in range(ctx.max_steps):
        step_msg = f"{file_stem} {step + 1}/{ctx.max_steps}"
        try:
            logger.start(step_msg)
            contents: list[object] = [
                ctx.template.format(skill=ctx.skill, path=file_path, code=current_txt),
            ]
            options = StructuredGenerationOptions(
                response_schema=LLMResponse,
                prefix=file_stem,
                spinner_msg=f"{ctx.func_name} LLM call {step + 1}",
                system_instruction="",
                tool_name=f"{ctx.func_name}",
                process_step=f"{step}",
                target_file=str(file_path),
                start_date=ctx.start_date,
            )
            response = ctx.llm.response(
                contents,
                options,
            )
            resp_typed = cast("LLMResponse", response)
            new_txt = resp_typed.code

            if ctx.check_func(current_txt, new_txt) == RunState.PASS:
                current_txt = new_txt
                status = RunState.PASS
                my_io.write_txt(new_txt, file_path)
                logger.end(step_msg, "")
            else:
                logger.warning(step_msg, "Failed")
        except Exception:
            logger.exception(step_msg, "Failed")

    return SummaryRow(
        file=file_path.name,
        status=("Edited" if status == RunState.PASS else "Failed"),
    )


async def run(
    file_path: Path,
    ctx: Context,
) -> SummaryRow:
    """Run chat task under semaphore limit and return SummaryRow."""
    async with ctx.semaphore:
        return await chat(
            file_path,
            ctx,
        )
