# src/coding_tools/docstring.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Scan code edits since last docstring pen.

AST audit of code match. Run jobs in sync with cap limit. File write access.
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
    from coding_tools.check import CheckParams


MAX_STEPS = 2
MIN_STEPS = 2

logger = my_logger.logger(__name__)


def check(params: CheckParams, run_output: RunOutput) -> RunOutput:
    """Run AST match on old and new text to spot code edits.

    Fail if text blank. Yield run output with state and sub func. File read.
    """
    func = __name__
    if not params.old_txt:
        msg = "Empty original text"
        logger.warning(func, msg)
        return replace(run_output, status=RunState.FAIL, msg=f"{func} - {msg}")
    if not params.new_txt:
        msg = "Empty new text"
        logger.warning(func, msg)
        return replace(run_output, status=RunState.FAIL, msg=f"{func} - {msg}")
    run_output = my_ast.match_codes(
        str(params.old_txt),
        str(params.new_txt),
        run_output,
    )
    return replace(run_output, sub_func=func, msg="")


def precheck(params: CheckParams, run_output: RunOutput) -> RunOutput:  # noqa: ARG001
    """Skip precheck step and yield skip state.

    No check run. Base return of input run output.
    """
    func = __name__
    return replace(run_output, status=RunState.SKIP, sub_func=func, msg="Skip precheck")
