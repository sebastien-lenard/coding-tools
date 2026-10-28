# src/coding_tools/my_run.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class EditState(Enum):
    """Give to which stage a file has been edited and saved, or not."""

    EDITED = "Edited"
    KEPT = "Kept"


class RunState(Enum):
    """Run state for process or block."""

    START = "Started"
    LIVE = "Live"
    DONE = "Done"
    FAIL = "Failed"
    PASS = "Passed"  # noqa: S105
    SKIP = "Skipped"


@dataclass
class RunOutput:
    """Gather the output run of a command, inc. exit, std.err and out."""

    func: str
    status: RunState
    input_path: Path | str | None = None
    output_path: Path | str | None = None
    log_path: Path | str | None = None
    step: str | int | None = None
    max_steps: int | None = None
    sub_func: str | None = None
    msg: str | None = None
    brief: str | None = None
    edited: EditState = EditState.KEPT
