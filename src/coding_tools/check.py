# src/coding_tools/check.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Check run ops.

Run state steps.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from coding_tools.my_run import RunOutput, RunState


@dataclass
class CheckParams:
    """Hold old, new text and file path for check step.

    Data sync. Base for run state. No file write, no API key.
    """

    old_txt: str | None
    new_txt: str | None
    file_path: Path


def default_check_func(_params: CheckParams, output: RunOutput) -> RunOutput:
    """Skip check and pass output with sub func tag set.

    Use mod name as tag, set state to skip. No file write, no API key.
    """
    return replace(output, sub_func=__name__.split(".")[-1], status=RunState.SKIP)
