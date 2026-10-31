# src/coding_tools/lead.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Launch and control code runs.

Handles args, switch to asked script, handles high-level errors and run exits.
"""

from __future__ import annotations

import argparse
import asyncio
import typing
from pathlib import Path
from typing import cast

from coding_tools import llm_emcee, my_import, my_io, my_logger, my_path
from coding_tools.llm_emcee import Context
from coding_tools.llm_protocol import LLMAPIError, LLMClientError, LLMServerError
from coding_tools.my_run import RunOutput, RunState

SKILL_PATH = "config/skills/TOOL.md"
SUMMARY_HEADERS = ("File", "Status", "Edited")
TEMPLATE_PATH = Path("config/templates/improve.md")
TOOL_SCRIPTS: typing.Final = {
    "pen-docstring": "coding_tools.docstring",
    "fix-lint": "coding_tools.lint",
    "fix-type": "coding_tools.static_type",
    "pen-test": "coding_tools.unit_test",
}

logger = my_logger.logger(__name__)


def context(args: argparse.Namespace) -> tuple[Context, list[RunOutput]]:
    func = "lead"
    try:
        mod_name = module_name(args)
    except ValueError as e:
        raise SystemExit(1) from e

    try:
        mod = my_import.import_module(mod_name)
    except (ImportError, OSError) as e:
        raise SystemExit(1) from e

    try:
        files: list[Path] = my_path.files(args.path)
    except FileNotFoundError as e:
        raise SystemExit(1) from e
    if not files:
        msg = f"No file at {args.path}"
        logger.error(None, msg)
        raise SystemExit(1)
    if args.test:
        file_paths_to_edit = my_path.unit_test_path(files)
        try:
            conftest = my_io.read_txt(my_path.conftest_path(args.path))
        except (RuntimeError, ValueError) as e:
            raise SystemExit(1) from e
    else:
        file_paths_to_edit = files
        conftest = ""

    try:
        skill = my_io.read_txt(skill_path(args), header=False)
        templ = my_io.read_txt(TEMPLATE_PATH, header=False)
    except (RuntimeError, ValueError) as e:
        raise SystemExit(1) from e

    return (
        Context(
            func_name=func,
            file_paths_to_edit=file_paths_to_edit,
            context_file_paths=[],
            conftest=conftest,
            skill=skill,
            check_func=mod.check,
            precheck_func=mod.precheck,
            template=templ,
            min_steps=mod.MIN_STEPS,
            max_steps=mod.MAX_STEPS,
        ),
        [
            RunOutput(
                func=func,
                sub_func="mc.init",
                status=RunState.PRESTART,
                input_path=f,
                step=0,
                max_steps=mod.MAX_STEPS,
            )
            for f in file_paths_to_edit
        ],
    )


def files(args: argparse.Namespace) -> list[Path]:
    """List path files. Raise value error if path bad."""
    return my_path.files(args.path)


def module_name(args: argparse.Namespace) -> str:
    """Map tool arg to script module name.

    Raise value error if tool key not found in tool scripts map.
    """
    mod_name = TOOL_SCRIPTS.get(str(args.tool))
    if not mod_name:
        msg = f"Bad tool: {args.tool}"
        logger.error(None, msg)
        raise ValueError(msg)
    return mod_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Switch run to asked script and control it",
    )
    parser.add_argument(
        "tool",
        type=str,
        help="Tool script to run (needed).",
    )
    parser.add_argument(
        "path",
        type=str,
        help="Target Python file or directory (needed).",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Target unit test files.",
    )
    return parser.parse_args()


def skill_path(args: argparse.Namespace) -> Path:
    """Get skill path for tool arg."""
    return Path(SKILL_PATH.replace("TOOL", args.tool).replace("-", "_"))


async def run() -> None:
    """Run async main flow.

    Parse args, get list of files, set up context, run tasks in loop, log summary.
    """
    func = __name__
    logger.start(func)

    args = parse_args()
    ctx, run_outputs = context(args)

    tasks = [
        llm_emcee.run(cast("Path", run_outputs[i].input_path), ctx, run_outputs[i])
        for i in range(len(ctx.file_paths_to_edit))
    ]
    try:
        run_outputs = await asyncio.gather(*tasks)
    except (LLMAPIError, LLMClientError, LLMServerError, Exception) as e:
        logger.summary_table(
            f"{args.tool.capitalize()} Summary",
            {
                "input_path": SUMMARY_HEADERS[0],
                "status": SUMMARY_HEADERS[1],
                "edited": SUMMARY_HEADERS[2],
            },
            run_outputs,
            formatters={
                "input_path": my_path.module_path,
                "status": lambda s: s.value,
                "edited": lambda ed: ed.value,
            },
        )
        raise SystemExit(1) from e

    for ro in run_outputs:
        if not ro.input_path and ro.output_path:
            ro.input_path = ro.output_path

    logger.summary_table(
        f"{args.tool.capitalize()} Summary",
        {
            "input_path": SUMMARY_HEADERS[0],
            "status": SUMMARY_HEADERS[1],
            "edited": SUMMARY_HEADERS[2],
        },
        run_outputs,
        formatters={
            "input_path": my_path.module_path,
            "status": lambda s: s.value,
            "edited": lambda e: e.value,
        },
    )
    logger.end(func)


def main() -> None:
    """Run async main loop via asyncio run."""
    my_logger.setup()
    asyncio.run(run())


if __name__ == "__main__":
    main()
