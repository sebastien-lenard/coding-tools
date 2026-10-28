# src/coding_tools/llm_emcee.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Handle prompt writing, sending to LLM, and check response and write it.

Audit of edits. Parallel runs with cap. File write access.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from coding_tools import (
    config,
    file_handler,
    llm_router,
    my_io,
    my_logger,
    workspace_stamper,
)
from coding_tools.llm_protocol import LLMResponse, StructuredGenerationOptions
from coding_tools.my_run import EditState, RunOutput, RunState

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol

PARALLEL_CALLS = 2
TEMPLATE_PATH = Path("config/templates/improve.md")
MAX_STEPS = 2
MIN_STEPS = 1
SUMMARY_HEADERS = ("File", "Pass", "Edited")

logger = my_logger.logger(__name__)


@dataclass
class CheckParams:
    """Params used by check function."""

    prev_txt: str | None
    new_txt: str | None
    file_path: Path


@dataclass
class Context:
    """Run context for updates.

    Holds paths, skills, check func, and semaphore. Needs LLM client.
    """

    func_name: str
    file_paths: list[Path]
    skill: str
    check_func: Callable[[CheckParams, RunOutput], RunOutput]
    precheck_func: Callable[[CheckParams, RunOutput], RunOutput]
    template: str
    max_steps: int
    min_steps: int
    start_date: str
    semaphore: asyncio.Semaphore
    llm: LLMClientProtocol


@dataclass
class SummaryRow:
    """Run summary per file.

    Maps file name to status string.
    """

    file: str
    passed: str
    edited: str


def init(
    func: str,
    path: Path | str,
    skill_path: Path | str,
    check_func: Callable[[CheckParams, RunOutput], RunOutput],
    precheck_func: Callable[[CheckParams, RunOutput], RunOutput],
    template_path: Path | str = TEMPLATE_PATH,
    max_steps: int = MAX_STEPS,
    min_steps: int = MIN_STEPS,
    parallel_calls: int = PARALLEL_CALLS,
) -> tuple[Context, RunOutput]:
    """Build and return Context for task.

    Read skill and template files. Raise OSError, UnicodeEncodeError, FileNotFoundError.
    """
    sub_func = "mc.init"
    file_paths = file_handler.files(path)
    if not file_paths:
        msg = f"No file at {path}"
        raise FileNotFoundError(msg)
    return Context(
        func_name=func,
        file_paths=file_paths,
        skill=workspace_stamper.strip_header(str(my_io.read_txt(skill_path))),
        check_func=check_func,
        precheck_func=precheck_func,
        template=workspace_stamper.strip_header(str(my_io.read_txt(template_path))),
        max_steps=max_steps,
        min_steps=min_steps,
        start_date=datetime.now().astimezone().strftime("%y-%m-%d"),
        semaphore=asyncio.Semaphore(parallel_calls),
        llm=llm_router.get_llm_client(),
    ), RunOutput(
        func=func,
        sub_func=sub_func,
        status=RunState.START,
        input_path=path,
        step=0,
        max_steps=max_steps,
    )


async def chat(
    file_path: Path,
    ctx: Context,
    run_output: RunOutput,
) -> RunOutput:
    """Enhance file content via LLM in steps with checks.

    Read file text. Call LLM API, check result, and write file if pass.
    """
    try:
        current_txt = my_io.read_txt(file_path)
    except (OSError, UnicodeEncodeError):
        logger.exception(None, "")
        return replace(run_output, status=RunState.FAIL, msg="Bad file")

    file_stem = file_path.stem
    python_version = config.python_version(file_path)
    python_version = (
        f"Python: {config.python_version(file_path)}\n"
        if file_path.suffix == ".py" and python_version
        else ""
    )
    check_params = CheckParams(prev_txt=current_txt, new_txt="", file_path=file_path)
    run_output = ctx.precheck_func(check_params, run_output)
    if run_output.status == RunState.PASS:
        msg = ", saved fixes." if run_output.edited == EditState.EDITED else "."
        msg = f"Passed precheck{msg} No call to LLM. File {file_path.name}"
        logger.end(ctx.func_name, msg)
        return replace(
            run_output,
            msg="Passed precheck, saved fixes",
        )

    for step in range(ctx.max_steps):
        run_output = replace(run_output, step=(step + 1))
        step_msg = f"{file_stem} {step + 1}/{ctx.max_steps}"
        try:
            logger.start(step_msg)
            contents: list[object] = [
                ctx.template.format(
                    python_version=python_version,
                    skill=ctx.skill,
                    path=file_path,
                    code=current_txt,
                ),
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
            check_params = replace(check_params, new_txt=resp_typed.code)
            run_output = ctx.check_func(check_params, run_output)
            if run_output.status == RunState.PASS:
                check_params = replace(
                    check_params,
                    prev_txt=check_params.new_txt,
                    new_txt="",
                )
                my_io.write_txt(str(check_params.prev_txt), file_path)
                run_output = replace(run_output, edited=EditState.EDITED)
                if step + 1 >= ctx.min_steps:
                    logger.end(file_path.name, f"Passed after {step + 1} steps")
                    break

        except Exception:
            run_output = replace(run_output, status=RunState.FAIL, msg="Error")
            logger.exception(step_msg, "Failed")

    return run_output


async def run(
    file_path: Path,
    ctx: Context,
    run_output: RunOutput,
) -> RunOutput:
    """Run chat task under semaphore limit and return SummaryRow."""
    async with ctx.semaphore:
        return await chat(
            file_path,
            ctx,
            run_output,
        )
