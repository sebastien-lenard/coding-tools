# src/coding_tools/lint.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Run lint checks and fix rules.

Writes file, calls ruff via my_ruff. Needs file path and check params.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from coding_tools import log, my_io, my_ruff
from coding_tools.log import Verbose
from coding_tools.my_run import EditState, RunOutput, RunState

if TYPE_CHECKING:
    from coding_tools.check import CheckParams

MAX_STEPS = 1
MIN_STEPS = 1

logger = log.logger(__name__)


def check(params: CheckParams, run_output: RunOutput) -> RunOutput:
    """Write file if new text given and run ruff.

    Fail if file miss. Write file via my_io. Run my_ruff.
    """
    if not params.file_path.is_file():
        logger.warning("No file %s", params.file_path)
        return replace(run_output, status=RunState.FAIL, msg="Bad file")
    if params.new_txt:
        my_io.write_txt(
            str(params.new_txt),
            params.file_path,
            verbose=Verbose.VV,
        )
        run_output = replace(run_output, edited=EditState.EDITED)
    return my_ruff.run(file_path=params.file_path, run_output=run_output)


def precheck(params: CheckParams, run_output: RunOutput) -> RunOutput:
    """Run check before lint pass.

    Call check with params and run output. Yield run output.
    """
    return check(params, run_output)
