# src/coding_tools/llm_emcee.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Send prompt to LLM, parse response, write edits.

Audit of edits. Run task in parallel with cap. File write access. Needs LLM API key.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

from coding_tools import conf, llm_protocol, llm_router, my_io, my_logger, my_path
from coding_tools.check import CheckParams, default_check_func
from coding_tools.my_logger import Verbose
from coding_tools.my_run import EditState, RunOutput, RunState

if TYPE_CHECKING:
    from coding_tools.llm_protocol import LLMClientProtocol


MAX_STEPS = 2
MIN_STEPS = 1
PARALLEL_CALLS = 2


logger = my_logger.logger(__name__)


@dataclass
class Context:
    """Run context for updates.

    Holds paths, skills, check func, and semaphore. Needs LLM client.
    """

    func_name: str
    file_paths_to_edit: list[Path] = field(default_factory=list)
    context_file_paths: list[Path] = field(default_factory=list)
    conftest: str = ""
    msg: str = ""
    skill: str = ""
    tips: str = ""
    check_func: Callable[[CheckParams, RunOutput], RunOutput] = default_check_func
    precheck_func: Callable[[CheckParams, RunOutput], RunOutput] = default_check_func
    template: str = ""
    max_steps: int = MAX_STEPS
    min_steps: int = MIN_STEPS
    start_date: str = datetime.now().astimezone().strftime("%y-%m-%d")
    semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(PARALLEL_CALLS),
    )
    llm: LLMClientProtocol = field(default=llm_router.get_llm_client())


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
        if my_path.is_unit_test(file_path):
            context_txt = my_io.read_txt(my_path.src_path(file_path))
        else:
            context_txt = ""
    except (OSError, UnicodeEncodeError):
        logger.exception(None, "")
        return replace(run_output, status=RunState.FAIL, msg="Bad file")

    file_stem = file_path.stem
    python_version = conf.python_version(file_path)
    python_version = (
        f"Python: {conf.python_version(file_path)}\n"
        if file_path.suffix == ".py" and python_version
        else ""
    )
    check_params = CheckParams(old_txt=current_txt, new_txt="", file_path=file_path)
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
            req: str = ctx.template.format(
                msg="",
                python_version=python_version,
                skill=ctx.skill,
                tips=run_output.brief,
                files_to_edit=current_txt,
                context_files=context_txt,
                conftest=ctx.conftest,
            )
            params = llm_protocol.LLMCallParams(
                response_schema=llm_protocol.LLMResponse,
                prefix=file_stem,
                tool_name=f"{ctx.func_name}",
                process_step=f"{step}",
                target_file=str(file_path),
            )
            resp = await ctx.llm.call(
                req,
                params,
            )
            check_params = replace(check_params, new_txt=resp.edited_files)
            run_output = ctx.check_func(check_params, run_output)
            if run_output.status == RunState.PASS:
                check_params = replace(
                    check_params,
                    old_txt=check_params.new_txt,
                    new_txt="",
                )
                my_io.write_txt(
                    str(check_params.old_txt),
                    file_path,
                    verbose=Verbose.VV,
                )
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
    """Run chat task under semaphore limit and return RunOutput.

    Calls chat async. Uses ctx.semaphore to cap tasks.
    """
    async with ctx.semaphore:
        return await chat(
            file_path,
            ctx,
            run_output,
        )
