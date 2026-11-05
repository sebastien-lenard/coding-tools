# src/coding_tools/lead.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Launch and control code runs.

Handles args, switch to asked script, handles high-level errors and run exits.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_tools import conf, llm_emcee, my_import, my_io, my_logger, my_path
from coding_tools.conf import ToolConf
from coding_tools.llm_emcee import Context
from coding_tools.llm_protocol import LLMAPIError, LLMClientError, LLMServerError
from coding_tools.my_run import RunOutput, RunState

if TYPE_CHECKING:
    from coding_tools.conf import ToolConf

SKILL_PATH: Final[Path] = Path("conf/skills/TOOL.md")
SUMMARY_HEADERS: Final[tuple[str, str, str]] = ("File", "Status", "Edited")
TEMPLATE_PATH: Final[Path] = Path("conf/templates/improve.md")
TOOLS: Final[dict[str, ToolConf]] = conf.tools()


logger = my_logger.get_logger(__name__)


def context(args: argparse.Namespace) -> tuple[Context, list[RunOutput]]:
    """Get context and init run data from parsed args.

    Imports module, scans paths, reads conftest and skill files if tool needs LLM.
    Raises KeyError, ImportError, FileNotFoundError, or RuntimeError on bad input.
    """
    func = "lead"
    try:
        mod_name = TOOLS[str(args.tool)]["mod"]
    except KeyError as e:
        msg = f"Bad tool: {args.tool}"
        logger.exception(msg)
        raise ValueError(msg) from e

    try:
        mod = my_import.import_module(mod_name)
    except (ImportError, OSError) as e:
        msg = f"Failed import of {mod_name}"
        logger.exception(msg)
        raise RuntimeError(msg) from e

    try:
        files: list[Path] = my_path.files(args.path)
    except FileNotFoundError as e:
        msg = f"Missing input files at {args.path}"
        logger.exception(msg)
        raise FileNotFoundError(msg) from e
    root_dir = my_path.root_dir(files[0])

    if args.test:
        file_paths_to_edit = my_path.unit_test_path(files)
        try:
            conftest = my_io.read_txt(my_path.conftest_path(args.path))
        except (RuntimeError, ValueError) as e:
            msg = rf"Missing tests\conftest.py in repo of {args.path}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
    else:
        file_paths_to_edit = files
        conftest = ""

    skill = ""
    templ = ""
    if TOOLS[str(args.tool)]["llm"] == "True":
        try:
            skill = my_io.read_txt(skill_path(args), header=False)
        except (RuntimeError, ValueError) as e:
            msg = f"Missing skill at {skill_path(args)}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
        try:
            templ = my_io.read_txt(TEMPLATE_PATH, header=False)
        except (RuntimeError, ValueError) as e:
            msg = f"Missing template at {TEMPLATE_PATH}"
            logger.exception(msg)
            raise RuntimeError(msg) from e

    return (
        Context(
            func_name=func,
            root_dir=root_dir,
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
                root_dir=root_dir,
                step=0,
                max_steps=mod.MAX_STEPS,
            )
            for f in file_paths_to_edit
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI args for tool and target path.

    Takes tool name and path. Accepts --test flag for unit test files.
    """
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
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity: -v for INFO, -vv for DEBUG",
    )
    return parser.parse_args()


def skill_path(args: argparse.Namespace) -> Path:
    """Get skill path for tool arg by name replacement.

    Maps hyphens to underscores in tool name under SKILL_PATH parent dir.
    """
    tool_name = str(args.tool).replace("-", "_")
    return SKILL_PATH.parent / f"{tool_name}.md"


async def run() -> None:
    """Run async main flow.

    Parse args, get file list, set up context, run tasks in loop, log summary.
    Catches LLM and general errors, prints summary table, exits on failure.
    """
    args = parse_args()
    logger.info("", extra={"leg": "start", "tool": args.tool})

    my_logger.set_level(logging.getLogger(), args.verbose)
    try:
        ctx, run_outputs = context(args)
    except Exception as e:
        msg = "Failed context"
        logger.exception(msg)
        logger.info("", extra={"leg": "fail", "tool": args.tool})
        raise SystemExit(1) from e

    try:
        run_outputs = await llm_emcee.run(ctx, run_outputs)
    except (LLMAPIError, LLMClientError, LLMServerError, Exception) as e:
        msg = str(e)
        logger.exception(msg)
        logging.getLogger().setLevel(logging.INFO)
        logger.info(
            "\n%s",
            my_logger.summary_table(
                f"{args.tool.capitalize()} Summary",
                {
                    "input_path": SUMMARY_HEADERS[0],
                    "status": SUMMARY_HEADERS[1],
                    "edited": SUMMARY_HEADERS[2],
                },
                run_outputs,
                formatters={
                    "input_path": lambda p: my_path.rel_path(p) if p else "",
                    "status": lambda s: s.value,
                    "edited": lambda ed: ed.value,
                },
            ),
        )
        logger.info("", extra={"leg": "fail", "tool": args.tool})
        raise SystemExit(1) from e

    for ro in run_outputs:
        if not ro.input_path and ro.output_path:
            ro.input_path = ro.output_path

    logging.getLogger().setLevel(logging.INFO)
    logger.info(
        "\n%s",
        my_logger.summary_table(
            f"{args.tool.capitalize()} Summary",
            {
                "input_path": SUMMARY_HEADERS[0],
                "status": SUMMARY_HEADERS[1],
                "edited": SUMMARY_HEADERS[2],
            },
            run_outputs,
            formatters={
                "input_path": lambda p: my_path.rel_path(p) if p else "",
                "status": lambda s: s.value,
                "edited": lambda e: e.value,
            },
        ),
    )
    logger.info("", extra={"leg": "end", "tool": args.tool})


def main() -> None:
    """Run async main loop via asyncio run.

    Sets up logger and runs async run function.
    """
    my_logger.setup()
    asyncio.run(run())


if __name__ == "__main__":
    main()
