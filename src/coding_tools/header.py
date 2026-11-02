# src/coding_tools/header.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from coding_tools import comment as c
from coding_tools import my_io, my_logger, my_path, my_string, txt
from coding_tools.my_run import EditState, RunOutput, RunState

if TYPE_CHECKING:
    from coding_tools.check import CheckParams

MAX_STEPS = 10
MIN_STEPS = 1

logger = my_logger.logger(__name__)


def check(params: CheckParams, run_output: RunOutput) -> RunOutput:

    if not run_output.input_path or not run_output.root_dir:
        return replace(run_output, status=RunState.FAIL, msg="Bad file")
    old_txt = my_string.my_str(params.old_txt)
    path = my_path.rel_path(run_output.input_path, run_output.root_dir)
    if c.head(old_txt) and not c.is_comment_or_blank(c.head(old_txt), path.suffix):
        msg = f"Bad txt with some lines other than comments for {path}"
        raise ValueError(msg)
    new_txt = c.strip_path_and_license(old_txt)
    new_info = (
        f"{c.comment(path.as_posix(), path.suffix)}"
        f"{c.spdx_copyright(run_output.root_dir, path.suffix)}"
        f"{c.spdx_license(run_output.root_dir, path.suffix)}"
    )
    new_txt = txt.insert(new_txt, new_info, c.head_insert_line(new_txt))
    if new_txt == params.old_txt:
        return replace(run_output, status=RunState.PASS)
    my_io.write_txt(new_txt, run_output.input_path)
    return replace(run_output, status=RunState.PASS, edited=EditState.EDITED)


def precheck(params: CheckParams, run_output: RunOutput) -> RunOutput:
    return check(params, run_output)
