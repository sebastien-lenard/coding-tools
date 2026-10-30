# src/coding_tools/lead.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Launch and control code runs.

Handles arguments, switch to asked script, handles high-level errors and run exits.
"""

from __future__ import annotations

import argparse
import asyncio
import typing
from pathlib import Path

from coding_tools import llm_emcee, my_import, my_io, my_logger, my_path
from coding_tools.llm_emcee import Context
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


def files(args: argparse.Namespace) -> list[Path]:
    """Raise ValueError."""
    return my_path.files(args.path)


def module_name(args: argparse.Namespace) -> str:
    mod_name = TOOL_SCRIPTS.get(str(args.tool))
    if not mod_name:
        msg = f"Bad tool: {args.tool}"
        logger.error(None, msg)
        raise ValueError(msg)
    return mod_name


def skill_path(args: argparse.Namespace) -> Path:
    return Path(SKILL_PATH.replace("TOOL", args.tool).replace("-", "_"))


async def run() -> None:
    """Run async main flow.

    Parse arguments, get target files, cap to a max parallel runs.
    Exit if target missing or empty.
    """
    func = __name__
    logger.start(func)

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
    args = parser.parse_args()

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

    ctx = Context(
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
    )
    run_output = RunOutput(
        func=func,
        sub_func="mc.init",
        status=RunState.START,
        input_path=args.path,
        step=0,
        max_steps=mod.MAX_STEPS,
    )

    tasks = [llm_emcee.run(f, ctx, run_output) for f in ctx.file_paths_to_edit]
    run_outputs = await asyncio.gather(*tasks)

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
    """Run async main loop via asyncio.run."""
    my_logger.setup()
    asyncio.run(run())


if __name__ == "__main__":
    main()
