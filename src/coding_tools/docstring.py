# src/coding_tools/docstring.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Check if code had been edited after automatic penning of docstrings using a LLM.

AST check of unexpected edits of code. Parallel runs with cap.
Writes files.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from coding_tools import (
    my_ast,
    my_logger,
)
from coding_tools.my_run import RunOutput, RunState

if TYPE_CHECKING:
    from coding_tools.llm_emcee import CheckParams


MAX_STEPS = 2
MIN_STEPS = 2

logger = my_logger.logger(__name__)


def check(params: CheckParams, run_output: RunOutput) -> RunOutput:
    """Don't use file_path in params."""
    func = __name__
    if not params.prev_txt:
        msg = "Empty original text"
        logger.warning(func, msg)
        return replace(run_output, status=RunState.FAIL, msg=f"{func} - {msg}")
    if not params.new_txt:
        msg = "Empty new text"
        logger.warning(func, msg)
        return replace(run_output, status=RunState.FAIL, msg=f"{func} - {msg}")
    run_output = my_ast.match_codes(
        str(params.prev_txt),
        str(params.new_txt),
        run_output,
    )
    return replace(run_output, sub_func=func, msg="")


def precheck(params: CheckParams, run_output: RunOutput) -> RunOutput:  # noqa: ARG001
    func = __name__
    return replace(run_output, status=RunState.SKIP, sub_func=func, msg="Skip precheck")
