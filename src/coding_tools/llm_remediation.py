# src/coding_tools/llm_remediation.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Core workflow engine and stage runner using an object-oriented LLM remediator."""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from coding_tools.gemini_client import (
    CACHE_ALLOWED,
    TestGenerationResponse,
    build_contents_list,
    create_text_part,
    load_skill,
)
from coding_tools.llm_protocol import StructuredGenerationOptions
from coding_tools.llm_router import get_llm_client
from coding_tools.parsers import (
    extract_pytest_warnings,
    parse_pytest_results,
    process_and_save_code,
    read_local_files,
    run_pytest_command,
    validate_llm_code,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_tools.llm_protocol import LLMClientProtocol

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Explicit tri-state outcomes for workflow stages."""

    SUCCESS = auto()
    FAILED = auto()
    FIXED = auto()


@dataclass
class WorkflowContext:
    """Encapsulate context and paths for workflow execution."""

    test_file_path: str
    source_file_path: str
    prefix: str
    allow_llm: bool


@dataclass
class StageConfig:
    """Configuration for a generic workflow stage execution."""

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
    """Engine managing workflow execution and protocol client binding."""

    def __init__(
        self,
        client: LLMClientProtocol | None = None,
        model_name: str = "gemini-3.5-flash-lite",
    ) -> None:
        self.client: LLMClientProtocol = (
            client if client is not None else get_llm_client(model_name)
        )
        self.model_name = model_name

    def is_syntactically_valid(self, code_content: str) -> bool:
        """Check if the code string is valid Python syntax."""
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
        """Build the appropriate contents list for the LLM remediation request."""
        if stage.build_custom_contents:
            contents_list = stage.build_custom_contents(
                ctx.test_file_path,
                ctx.source_file_path,
                test_content,
                output,
            )
        else:
            contents_list = [
                create_text_part(
                    (
                        f"--- Current unit test script "
                        f"({Path(ctx.test_file_path).name}) ---\n{test_content}"
                    ),
                ),
                create_text_part(text=f"--- {stage.name} output ---\n{output}"),
                create_text_part(
                    (
                        f"MANDATORY INSTRUCTION: You MUST modify the code to "
                        f"resolve all {stage.name} errors. "
                        f"Do NOT return the exact same code."
                    ),
                ),
            ]

        if identical_attempts > 0:
            contents_list.append(
                create_text_part(
                    (
                        "ERROR: Your previous output was IDENTICAL to the existing "
                        "file, failing to fix the error. "
                        "You are required to rewrite or update the failing test "
                        "function implementation."
                    ),
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
        """Iterate with the LLM to fix test failures."""
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
                    response_schema=TestGenerationResponse,
                    prefix=ctx.prefix,
                    spinner_msg=(f"Sending {stage.name} fix request to LLM..."),
                    system_instruction=system_instruction_text,
                    cache_name=cache_name,
                )
                raw_resp = self.client.generate_structured_response(
                    contents_list=contents_list,
                    options=options,
                )
                parsed_resp = cast("TestGenerationResponse", raw_resp)
            except Exception:
                logger.exception(
                    "[%s] Failed during structured LLM execution for %s",
                    ctx.prefix,
                    stage.name,
                )
                if CACHE_ALLOWED:
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
                if CACHE_ALLOWED:
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
                    if CACHE_ALLOWED:
                        self.client.cleanup_files(uploaded_files, ctx.prefix)
                    return WorkflowStatus.FAILED, "No solution"

                logger.warning(
                    "[%s] LLM returned identical code to the current file. "
                    "Resending request...",
                    ctx.prefix,
                )
                identical_attempts += 1
                continue

            break

        if CACHE_ALLOWED:
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
        """Execute, evaluate, and remediate a single workflow stage."""
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
        """Set up optional file caching using the bound client adapter."""
        return self.client.setup_cache(source_file_path, prefix)

    def run_pytest_stage(
        self,
        cache_name: str | None,
        uploaded_files: list[Any],
        ctx: WorkflowContext,
    ) -> tuple[WorkflowStatus, str, str]:
        """Execute the pytest and coverage stage."""

        def run_pytest() -> str:
            run_pytest_command(
                ctx.test_file_path,
                ctx.source_file_path,
                ctx.prefix,
            )
            _, _, py_out = read_local_files(
                ctx.test_file_path,
                ctx.source_file_path,
                ctx.prefix,
            )
            return py_out

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
            logger.info(
                "[%s] Pytest check evaluation | Summary: '%s' | "
                "100%% Coverage: %s | Missing: %s | Tests Passed: %s | "
                "Syntax Error: %s",
                ctx.prefix,
                summary,
                is_100_percent,
                missing_lines,
                tests_passed,
                is_syntax_error,
            )
            if is_syntax_error:
                logger.error(
                    "[%s] Syntax/Collection error details:\n%s",
                    ctx.prefix,
                    syntax_details,
                )
                return False
            summary_lower = summary.lower()
            has_error = "error" in summary_lower or "error" in output.lower()
            has_failure = "failed" in summary_lower
            has_warning = extract_pytest_warnings(output) != "None"
            return not (has_error or has_failure or not is_100_percent or has_warning)

        def build_pytest_contents(
            t_path: str,
            s_path: str,
            t_content: str,
            py_out: str,
        ) -> list[Any]:
            _, _, _, _, is_syntax_error, syntax_error_details = parse_pytest_results(
                py_out,
                s_path,
            )
            if is_syntax_error:
                return [
                    create_text_part(
                        text=(
                            f"--- Current unit test script "
                            f"({Path(t_path).name}) ---\n{t_content}"
                        ),
                    ),
                    create_text_part(
                        text=(
                            "--- Pytest Syntax/Collection "
                            f"Error Traceback ---\n{syntax_error_details}"
                        ),
                    ),
                    create_text_part(
                        text=(
                            "The unit test script contains a fatal Python "
                            "SyntaxError or collection issue preventing pytest. "
                            "Please fix and return complete script."
                        ),
                    ),
                ]
            return build_contents_list(t_path, s_path, t_content, "", py_out)

        return self.run_workflow_stage(
            cache_name,
            uploaded_files,
            ctx,
            StageConfig(
                name="Pytest/Coverage",
                run_command=run_pytest,
                is_success=check_pytest,
                skill_filename="unit_test_generation.md",
                build_custom_contents=build_pytest_contents,
            ),
        )
