# src/coding_tools/llm_remediation.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Run LLM remediation workflow stages, check syntax, and execute tests.

Handles preflight checks, test execution with coverage, and LLM code updates.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from coding_tools.llm_prompts import build_contents_list, load_skill
from coding_tools.llm_protocol import (
    LLMResponse,
    StructuredGenerationOptions,
)
from coding_tools.llm_router import get_llm_client
from coding_tools.parsers import (
    parse_pytest_results,
    process_and_save_code,
    read_local_files,
    run_preflight_compliance_and_validation,
    validate_llm_code,
)
from coding_tools.workspace_guard import WorkspaceGuard

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_tools.llm_protocol import LLMClientProtocol

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Tri-state outcomes for workflow stages."""

    SUCCESS = auto()
    FAILED = auto()
    FIXED = auto()


@dataclass
class WorkflowContext:
    """Store context and paths for workflow execution."""

    test_file_path: str
    source_file_path: str
    prefix: str
    allow_llm: bool


@dataclass
class StageConfig:
    """Store config for workflow stage execution."""

    name: str
    run_command: Callable[[], str]
    is_success: Callable[[str], bool]
    skill_filename: str
    build_custom_contents: (
        Callable[
            ...,
            list[Any],
        ]
        | None
    ) = None


class LLMRemediator:
    """Manage workflow execution and protocol client binding.

    Handles LLM client calls, syntax checks, caching, and test stage loops.
    """

    def __init__(
        self,
        client: LLMClientProtocol | None = None,
        model_name: str | None = None,
    ) -> None:
        self.client: LLMClientProtocol = (
            client if client is not None else get_llm_client(model_name)
        )

    def is_syntactically_valid(self, code_content: str) -> bool:
        """Check if code string is valid Python syntax via AST parse.

        False on SyntaxError.
        """
        try:
            ast.parse(code_content)
        except SyntaxError:
            return False
        return True

    def _build_workflow_contents(
        self,
        ctx: WorkflowContext,
        stage: StageConfig,
        test_content: str,
        output: str,
        identical_attempts: int,
    ) -> list[Any]:
        """Build contents list for LLM remediation request.

        Appends error note if attempts are identical.
        """
        if stage.build_custom_contents:
            contents_list = stage.build_custom_contents(
                ctx.test_file_path,
                ctx.source_file_path,
                test_content,
                output,
            )
        else:
            contents_list = [
                (
                    f"--- Current unit test script "
                    f"({Path(ctx.test_file_path).name}) ---\n{test_content}"
                ),
                f"--- {stage.name} output ---\n{output}",
            ]

        if identical_attempts > 0:
            contents_list.append(
                (
                    "ERROR: Your previous output was IDENTICAL to the existing "
                    "file, failing to fix the error. "
                    "You are required to rewrite or update the failing test "
                    "function implementation."
                ),
            )
        return contents_list

    def _process_llm_remediation(
        self,
        ctx: WorkflowContext,
        stage: StageConfig,
        cache_name: str | None,
        uploaded_files: list[Any],
        output: str,
    ) -> tuple[WorkflowStatus, str]:
        """Iterate with LLM to fix test failures and validate code.

        Retries on identical output up to limit, cleans up cache on exit.
        """
        identical_attempts = 0
        max_identical_allowed = 1

        while True:
            test_content = Path(ctx.test_file_path).read_text(encoding="utf-8")
            contents_list = self._build_workflow_contents(
                ctx,
                stage,
                test_content,
                output,
                identical_attempts,
            )

            system_instruction_text = load_skill(stage.skill_filename)

            try:
                options = StructuredGenerationOptions(
                    response_schema=LLMResponse,
                    prefix=ctx.prefix,
                    spinner_msg=(f"Sending {stage.name} fix request to LLM..."),
                    system_instruction=system_instruction_text,
                    cache_name=cache_name,
                )
                raw_resp = self.client.generate_structured_response(
                    contents_list=contents_list,
                    options=options,
                )
                parsed_resp = cast("LLMResponse", raw_resp)
            except Exception:
                logger.exception(
                    "[%s] Failed during structured LLM execution for %s",
                    ctx.prefix,
                    stage.name,
                )
                if self.client.supports_caching:
                    self.client.cleanup_files(uploaded_files, ctx.prefix)
                return WorkflowStatus.FAILED, "FAILED"

            is_valid, validation_reason = validate_llm_code(parsed_resp.code)
            if not is_valid:
                logger.warning(
                    "[%s] LLM returned invalid/incorrect code for %s. "
                    "Validation failure reason: %s. Skipping update.",
                    ctx.prefix,
                    stage.name,
                    validation_reason,
                )
                logger.debug(
                    "[%s] Rejected LLM code payload:\n%s",
                    ctx.prefix,
                    parsed_resp.code,
                )
                if self.client.supports_caching:
                    self.client.cleanup_files(uploaded_files, ctx.prefix)
                return WorkflowStatus.FAILED, "FAILED"

            if parsed_resp.code.strip() == test_content.strip():
                if identical_attempts >= max_identical_allowed:
                    logger.error(
                        "[%s] Aborting workflow stage '%s'. LLM repeatedly "
                        "returned identical code despite warnings.\n"
                        "Last error output:\n%s",
                        ctx.prefix,
                        stage.name,
                        output,
                    )
                    if self.client.supports_caching:
                        self.client.cleanup_files(uploaded_files, ctx.prefix)
                    return WorkflowStatus.FAILED, "No solution"

                logger.warning(
                    "[%s] LLM returned identical code to the file. Resending request.",
                    ctx.prefix,
                )
                identical_attempts += 1
                continue

            break

        if self.client.supports_caching:
            self.client.cleanup_files(uploaded_files, ctx.prefix)

        logger.info("[%s] LLM response: %s", ctx.prefix, parsed_resp.message)
        process_and_save_code(parsed_resp.code, ctx.test_file_path, ctx.prefix)
        return WorkflowStatus.FIXED, "FIXED"

    def run_workflow_stage(
        self,
        cache_name: str | None,
        uploaded_files: list[Any],
        ctx: WorkflowContext,
        stage: StageConfig,
    ) -> tuple[WorkflowStatus, str, str]:
        """Run, evaluate, and remediate workflow stage.

        Skips LLM call if not allowed.
        """
        logger.info("[%s] Running %s stage...", ctx.prefix, stage.name)
        output = stage.run_command()

        if stage.is_success(output):
            logger.info("[%s] %s passed cleanly.", ctx.prefix, stage.name)
            return WorkflowStatus.SUCCESS, stage.name, "SUCCESS"

        if not ctx.allow_llm:
            logger.warning(
                "[%s] %s failed after all LLM authorized calls.",
                ctx.prefix,
                stage.name,
            )
            return WorkflowStatus.FAILED, stage.name, "FAILED"

        logger.info(
            "[%s] Reason for LLM call: %s issues detected.",
            ctx.prefix,
            stage.name,
        )

        status_enum, status_msg = self._process_llm_remediation(
            ctx,
            stage,
            cache_name,
            uploaded_files,
            output,
        )
        return status_enum, stage.name, status_msg

    def setup_cache(
        self,
        source_file_path: str,
        prefix: str,
    ) -> tuple[str | None, list[Any]]:
        """Set up optional file caching using bound client adapter."""
        return self.client.setup_cache(source_file_path, prefix)

    def _handle_preflight_failure(
        self,
        cache_name: str | None,
        uploaded_files: list[Any],
        ctx: WorkflowContext,
        preflight_errors: list[str],
    ) -> tuple[WorkflowStatus, str, str]:
        """Handle pre-pytest run validation failures and route to LLM."""
        logger.warning(
            "[%s] Pre-pytest run static checks failed. "
            "Bypassing pytest and routing to LLM...",
            ctx.prefix,
        )
        test_stem = Path(ctx.test_file_path).stem
        Path(f"unit-test-{test_stem}.txt").write_text(
            "\n".join(preflight_errors),
            encoding="utf-8",
        )

        if not ctx.allow_llm:
            return WorkflowStatus.FAILED, "Pytest/Coverage", "FAILED"

        error_output = "\n".join(preflight_errors)
        status_enum, status_msg = self._process_llm_remediation(
            ctx,
            StageConfig(
                name="Pytest/Coverage",
                run_command=lambda: error_output,
                is_success=lambda _: False,
                skill_filename="unit_test_generation.md",
            ),
            cache_name,
            uploaded_files,
            error_output,
        )
        return status_enum, "Pytest/Coverage", status_msg

    def _build_pytest_run_command(self, ctx: WorkflowContext) -> Callable[[], str]:
        """Build pytest command runner wrapped with guard with coverage enabled."""
        guard = WorkspaceGuard(project_path=Path.cwd())

        def run_pytest_with_guard() -> str:
            passed, guard_errors = guard.execute_test_and_guard(
                ctx.test_file_path,
                ctx.prefix,
                run_coverage=True,
                source_file_path=ctx.source_file_path,
            )
            _, _, py_out = read_local_files(
                ctx.test_file_path,
                ctx.source_file_path,
                ctx.prefix,
            )
            if not passed and guard_errors:
                py_out += (
                    "\n\n--- Runtime Workspace Guard Violations (Priority 6) ---\n"
                    + "\n".join(guard_errors)
                )
            return py_out

        return run_pytest_with_guard

    def _evaluate_pytest_success(self, ctx: WorkflowContext) -> Callable[[str], bool]:
        """Evaluate pytest output against coverage, errors, and pollution rules."""

        def check_pytest(output: str) -> bool:
            (
                summary,
                missing_lines,
                tests_passed,
                is_100_percent,
                is_syntax_error,
                syntax_details,
            ) = parse_pytest_results(
                output,
                ctx.source_file_path,
            )
            summary_lower = summary.lower()
            has_error = "error" in summary_lower or "error" in output.lower()
            has_failure = "failed" in summary_lower
            has_pollution = "Runtime Workspace Guard Violations" in output

            status_label = (
                "PASSED"
                if (
                    tests_passed
                    and is_100_percent
                    and not has_pollution
                    and not has_error
                )
                else "FAILED"
            )
            logger.info(
                "[%s] Post-Pytest Run Synthesis Status: [%s] | Errors: %s | "
                "Pollution: %s | Failures: %s | Coverage: %s",
                ctx.prefix,
                status_label,
                "FAIL" if (has_error or is_syntax_error) else "PASS",
                "FAIL" if has_pollution else "PASS",
                "FAIL" if has_failure else "PASS",
                "PASS" if is_100_percent else f"FAIL ({missing_lines})",
            )

            if is_syntax_error:
                logger.error(
                    "[%s] Syntax/Collection error details:\n%s",
                    ctx.prefix,
                    syntax_details,
                )
                return False

            return not (has_error or has_failure or not is_100_percent or has_pollution)

        return check_pytest

    def _build_pytest_custom_contents(
        self,
        t_path: str,
        s_path: str,
        t_content: str,
        py_out: str,
    ) -> list[Any]:
        """Build custom contents payload dynamically filtering out passing checks."""
        _, _, _, _, is_syntax_error, syntax_error_details = parse_pytest_results(
            py_out,
            s_path,
        )
        if is_syntax_error:
            return [
                (
                    f"--- Current unit test script "
                    f"({Path(t_path).name}) ---\n{t_content}"
                ),
                (
                    "--- Pytest Syntax/Collection "
                    f"Error Traceback ---\n{syntax_error_details}"
                ),
                (
                    "The unit test script contains a fatal Python "
                    "SyntaxError or collection issue preventing pytest. "
                    "Please fix and return complete script."
                ),
            ]
        return build_contents_list(t_path, s_path, t_content, "", py_out)

    def run_pytest_stage(
        self,
        cache_name: str | None,
        uploaded_files: list[Any],
        ctx: WorkflowContext,
    ) -> tuple[WorkflowStatus, str, str]:
        """Run pre-pytest run compliance, pytest, coverage, and runtime guard."""
        preflight_ok, preflight_errors = run_preflight_compliance_and_validation(
            ctx.test_file_path,
            ctx.prefix,
        )
        if not preflight_ok:
            return self._handle_preflight_failure(
                cache_name,
                uploaded_files,
                ctx,
                preflight_errors,
            )

        run_cmd = self._build_pytest_run_command(ctx)
        check_func = self._evaluate_pytest_success(ctx)

        return self.run_workflow_stage(
            cache_name,
            uploaded_files,
            ctx,
            StageConfig(
                name="Pytest/Coverage",
                run_command=run_cmd,
                is_success=check_func,
                skill_filename="unit_test_generation.md",
                build_custom_contents=self._build_pytest_custom_contents,
            ),
        )
