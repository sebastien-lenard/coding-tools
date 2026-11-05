# src/coding_tools/my_run.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Track run states and file edit steps.

Safe helpers for run ops.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class EditState(Enum):
    """State of file edit and save step.

    Edited or kept.
    """

    EDITED = "Edited"
    KEPT = "Kept"


class RunState(Enum):
    """Run state for process or block.

    Start, live, done, fail, pass, skip, or prestart.
    """

    START = "Started"
    LIVE = "Live"
    DONE = "Done"
    FAIL = "Failed"
    PASS = "Passed"  # noqa: S105
    SKIP = "Skipped"
    PRESTART = "Not started"


@dataclass
class RunOutput:
    """Store run output data of a command.

    Holds func, status, paths, step counts, sub func, msg, brief, and edit state.
    """

    func: str
    status: RunState
    input_path: Path | None = None
    output_path: Path | None = None
    log_path: Path | None = None
    root_dir: Path | None = None
    step: str | int | None = None
    max_steps: int | None = None
    sub_func: str = ""
    msg: str = ""
    brief: str = ""
    edited: EditState = EditState.KEPT
