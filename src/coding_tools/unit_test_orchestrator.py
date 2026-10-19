# src/coding_tools/unit_test_orchestrator.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Orchestrate automated test generation, coverage, basedpyright, and ruff checks."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from google.genai import Client, errors
from google.genai.errors import ServerError

from coding_tools.gemini_remediation import (
    StageConfig,
    WorkflowContext,
    WorkflowStatus,
    run_pytest_stage,
    run_workflow_stage,
    setup_cache,
)
from coding_tools.gemini_service import CACHE_ALLOWED, cleanup_files
from coding_tools.parsers import (
    filter_ruff_output,
    parse_basedpyright_summary,
    run_basedpyright_command,
    run_ruff_command,
)

# Configure logging format and level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _evaluate_stage_status(
    status_enum: WorkflowStatus,
    stage_name: str,
    status: str,
) -> tuple[bool, str, str] | None:
    """Evaluate stage status enum and map to orchestrator response if non-success."""
    if status_enum == WorkflowStatus.FIXED:
        return False, stage_name, "FIXED"
    if status_enum == WorkflowStatus.FAILED:
        return False, stage_name, status
    return None


def _run_stage_chain(
    client: Client,
    cache_name: str | None,
    uploaded_files: list[Any],
    ctx: WorkflowContext,
) -> tuple[bool, str, str]:
    """Execute the sequence of workflow stages sequentially."""
    # --- STAGE 1: Pytest / Coverage ---
    res = _evaluate_stage_status(
        *run_pytest_stage(client, cache_name, uploaded_files, ctx),
    )
    if res is not None:
        return res

    # --- STAGE 2: Basedpyright Type Checking ---
    res = _evaluate_stage_status(
        *run_workflow_stage(
            client,
            cache_name,
            uploaded_files,
            ctx,
            StageConfig(
                name="Basedpyright",
                run_command=lambda: run_basedpyright_command(
                    ctx.test_file_path,
                    ctx.prefix,
                ),
                is_success=lambda out: (
                    "0 errors, 0 warnings, 0 notes" in parse_basedpyright_summary(out)
                ),
                skill_filename="basedpyright_correction.md",
            ),
        ),
    )
    if res is not None:
        return res

    # --- STAGE 3: Ruff Linting ---
    res = _evaluate_stage_status(
        *run_workflow_stage(
            client,
            cache_name,
            uploaded_files,
            ctx,
            StageConfig(
                name="Ruff",
                run_command=lambda: filter_ruff_output(
                    run_ruff_command(ctx.test_file_path, ctx.prefix),
                ),
                is_success=lambda out: (
                    ("Ruff Status: PASSED" in out or "All checks passed!" in out)
                    and "FAILED" not in out
                    and "error" not in out.lower()
                ),
                skill_filename="ruff_correction.md",
            ),
        ),
    )
    if res is not None:
        return res

    return True, "ALL_STAGES", "SUCCESS"


def execute_workflow(
    test_file_path: str = "tests/unit/test_dummy_target.py",
    source_file_path: str = "src/coding_tools/dummy_target.py",
    *,
    allow_gemini: bool = True,
) -> tuple[bool, str, str]:
    """Execute automated test generation, type checking, and linting workflow.

    Returns:
        tuple[bool, str, str]: (success, stage_name, status)

    """
    prefix = Path(test_file_path).name
    ctx = WorkflowContext(test_file_path, source_file_path, prefix, allow_gemini)

    with Client() as client:
        try:
            cache_name, uploaded_files = setup_cache(
                client,
                source_file_path,
                prefix,
            )

            success, stage_name, status = _run_stage_chain(
                client,
                cache_name,
                uploaded_files,
                ctx,
            )
            if not success:
                return False, stage_name, status

            if CACHE_ALLOWED:
                cleanup_files(client, uploaded_files, prefix)
        except (ServerError, errors.APIError):
            logger.exception(
                "[%s] Gemini API / Server Error encountered",
                prefix,
            )
            return False, "Pytest/Coverage", "API_ERROR"
        except (OSError, ValueError):
            logger.exception("[%s] File I/O or Value Error", prefix)
            raise
        except subprocess.SubprocessError:
            logger.exception("[%s] Subprocess Execution Error", prefix)
            raise
        else:
            return True, "ALL_STAGES", "SUCCESS"
