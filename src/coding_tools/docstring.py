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
from pathlib import Path

from coding_tools import (
    llm_emcee,
    my_ast,
    my_logger,
)
from coding_tools.my_logger import RunState

SKILL_PATH = Path("config/skills/docstring.md")
MAX_STEPS = 2
SUMMARY_HEADERS = ("File", "Status")

logger = my_logger.logger(__name__)


def check(prev_txt: str, new_txt: str) -> RunState:
    return my_ast.match_codes(prev_txt, new_txt)


async def async_main() -> None:
    """Run async main flow for docstring writer.

    Parse arguments, get target files, cap to 4 parallel runs.
    Exit if target missing or empty.
    """
    func = __name__
    func_name = "pen-docstring"
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
        ctx = llm_emcee.init(
            func_name=func_name,
            path=args.path,
            skill_path=SKILL_PATH,
            check_func=check,
            max_steps=MAX_STEPS,
        )
    except (OSError, UnicodeEncodeError) as e:
        logger.exception(None, "")
        logger.end(func)
        raise SystemExit(1) from e

    tasks = [llm_emcee.run(f, ctx) for f in ctx.file_paths]
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
