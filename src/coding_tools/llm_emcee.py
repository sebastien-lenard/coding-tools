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
from typing import TYPE_CHECKING, cast

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


logger = my_logger.get_logger(__name__)


@dataclass
class Context:
    """Run context for updates.

    Holds paths, skills, check func, and semaphore. Needs LLM client.
    """

    func_name: str
    root_dir: Path
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


@dataclass
class ChatStepParams:
    """Parameters for executing a single chat step."""

    file_path: Path
    file_stem: str
    ctx: Context
    run_output: RunOutput
    check_params: CheckParams
    current_txt: str
    context_txt: str
    python_version: str
    step: int


def _safe_call_func(
    func: Callable[..., RunOutput],
    *args: object,
    **kwargs: object,
) -> RunOutput | Exception:
    """Run check or precheck function. Catch any error."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.exception("", extra={"leg": "fail"})
        return e


async def _prepare_context_and_version(file_path: Path) -> tuple[str, str]:
    """Get context text and python version for chat prompt."""
    if my_path.is_unit_test(file_path):
        try:
            context_txt = my_io.read_txt(my_path.src_path(file_path))
        except (OSError, UnicodeEncodeError):
            logger.exception("Failed read src file %s", file_path)
            raise
    else:
        context_txt = ""

    python_version = conf.python_version(file_path)
    python_version_str = (
        f"Python: {python_version}\n"
        if file_path.suffix == ".py" and python_version
        else ""
    )
    return context_txt, python_version_str


async def _execute_chat_step(
    params: ChatStepParams,
) -> tuple[RunOutput, CheckParams, bool]:
    """Run single chat step, call LLM, check and save if pass."""
    file_path = params.file_path
    file_stem = params.file_stem
    ctx = params.ctx
    run_output = params.run_output
    check_params = params.check_params
    current_txt = params.current_txt
    context_txt = params.context_txt
    python_version = params.python_version
    step = params.step

    run_output = replace(run_output, step=(step + 1))
    extra = {
        "leg": "start",
        "file": file_path,
        "files_count": len(ctx.file_paths_to_edit),
        "step": step + 1,
        "max_steps": ctx.max_steps,
    }
    try:
        logger.info("", extra=extra)
        req: str = ctx.template.format(
            msg="",
            python_version=python_version,
            skill=ctx.skill,
            tips=run_output.brief,
            files_to_edit=current_txt,
            context_files=context_txt,
            conftest=ctx.conftest,
        )
        llm_params = llm_protocol.LLMCallParams(
            response_schema=llm_protocol.LLMResponse,
            prefix=file_stem,
            tool_name=f"{ctx.func_name}",
            process_step=f"{step}",
            target_file=str(file_path),
        )
        resp = await ctx.llm.call(
            req,
            llm_params,
        )
        check_params = replace(check_params, new_txt=resp.edited_files)
        res = _safe_call_func(ctx.check_func, check_params, run_output)
        if isinstance(res, Exception):
            return (
                replace(
                    run_output,
                    status=RunState.FAIL,
                    msg=f"Precheck error: {res}",
                ),
                check_params,
                False,
            )
        run_output = res
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
                logger.info(
                    "after {step + 1} steps",
                    extra=extra.update({"leg": "pass"}),
                )
                return run_output, check_params, True

    except Exception:
        run_output = replace(run_output, status=RunState.FAIL, msg="Error")
        logger.exception(
            "",
            extra=extra.update({"leg": "fail"}),
        )

    return run_output, check_params, False


async def chat(
    file_path: Path,
    ctx: Context,
    run_output: RunOutput,
) -> RunOutput:
    """Run chat steps to edit file via LLM.

    Read file, call LLM API, check result, and write file if pass. File write access.
    """
    try:
        current_txt = my_io.read_txt(file_path)
    except (RuntimeError, ValueError):
        logger.exception("reading file %s", file_path, extra={"leg": "fail"})
        return replace(run_output, status=RunState.FAIL, msg="Bad file")

    check_params = CheckParams(old_txt=current_txt, new_txt="", file_path=file_path)
    res = _safe_call_func(ctx.precheck_func, check_params, run_output)
    if isinstance(res, Exception):
        return replace(run_output, status=RunState.FAIL, msg=f"Precheck error: {res}")
    run_output = res

    if run_output.status == RunState.PASS:
        msg = ", saved fixes." if run_output.edited == EditState.EDITED else "."
        msg = f"precheck{msg} No call to LLM. File {file_path.name}"
        logger.info(
            msg,
            extra={
                "leg": "pass",
                "file": file_path,
                "files_count": len(ctx.file_paths_to_edit),
            },
        )
        return replace(
            run_output,
            msg="Passed precheck, saved fixes",
        )

    try:
        context_txt, python_version = await _prepare_context_and_version(file_path)
    except (OSError, UnicodeEncodeError):
        return replace(run_output, status=RunState.FAIL, msg="Bad file")

    file_stem = file_path.stem

    for step in range(ctx.max_steps):
        step_params = ChatStepParams(
            file_path=file_path,
            file_stem=file_stem,
            ctx=ctx,
            run_output=run_output,
            check_params=check_params,
            current_txt=current_txt,
            context_txt=context_txt,
            python_version=python_version,
            step=step,
        )
        run_output, check_params, should_break = await _execute_chat_step(
            step_params,
        )
        if should_break:
            break

    return run_output


async def run_chat(
    file_path: Path,
    ctx: Context,
    run_output: RunOutput,
) -> RunOutput:
    """Run chat task under semaphore limit.

    Calls chat async. Uses ctx.semaphore to cap tasks.
    """
    async with ctx.semaphore:
        return await chat(
            file_path,
            ctx,
            run_output,
        )


async def run(ctx: Context, run_outputs: list[RunOutput]) -> list[RunOutput]:
    """Run chat tasks in parallel with semaphore cap."""
    tasks = [run_chat(cast("Path", ro.input_path), ctx, ro) for ro in run_outputs]
    return await asyncio.gather(*tasks)
