# src/coding_tools/lead.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Launch and control code runs.

Handles arguments, switch to asked script, handles high-level errors and run exits.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
from typing import Final

from coding_tools import file_handler, llm_emcee, my_logger

SKILL_PATH = "config/skills/TOOL.md"
MAX_STEPS = 2
MIN_STEPS = 2
SUMMARY_HEADERS = ("File", "Status", "Edited")

TOOL_SCRIPTS: Final = {
    "pen-docstring": "coding_tools.docstring",
    "fix-lint": "coding_tools.lint",
}

logger = my_logger.logger(__name__)


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
    args = parser.parse_args()

    module_name = TOOL_SCRIPTS.get(args.tool)
    if not module_name:
        logger.error(func, f"Bad tool: {args.tool}")
        logger.end(func)
        raise SystemExit(1)

    try:
        mod = importlib.import_module(module_name)
    except (ImportError, OSError) as e:
        logger.exception(func, f"Import fail: {module_name}")
        logger.end(func)
        raise SystemExit(1) from e

    try:
        ctx, run_output = llm_emcee.init(
            func=args.tool,
            path=args.path,
            skill_path=SKILL_PATH.replace("TOOL", args.tool).replace("-", "_"),
            check_func=mod.check,
            precheck_func=mod.precheck,
            max_steps=mod.MAX_STEPS,
            min_steps=mod.MIN_STEPS,
        )
    except (OSError, UnicodeEncodeError) as e:
        logger.exception(None, "")
        logger.end(func)
        raise SystemExit(1) from e

    tasks = [llm_emcee.run(f, ctx, run_output) for f in ctx.file_paths]
    run_outputs = await asyncio.gather(*tasks)

    logger.summary_table(
        f"{args.tool.capitalize()} Summary",
        {
            "input_path": SUMMARY_HEADERS[0],
            "status": SUMMARY_HEADERS[1],
            "edited": SUMMARY_HEADERS[2],
        },
        run_outputs,
        formatters={"input_path": file_handler.module_path},
    )
    logger.end(func)


def main() -> None:
    """Run async main loop via asyncio.run."""
    my_logger.setup()
    asyncio.run(run())


if __name__ == "__main__":
    main()
