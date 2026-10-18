# src/coding_tools/unit_test_orchestrator.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Orchestrate automated test generation, coverage, basedpyright, and ruff checks."""

from __future__ import annotations

import ast
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from google.genai import Client, errors, types
from google.genai.errors import ServerError

from coding_tools.gemini_service import (
    CACHE_ALLOWED,
    MODEL_NAME,
    TestGenerationResponse,
    build_contents_list,
    cleanup_files,
    gemini_spinner,
    load_skill,
    upload_static_file,
    validate_file_uris,
)
from coding_tools.parsers import (
    extract_pytest_warnings,
    filter_ruff_output,
    is_valid_gemini_code,
    parse_basedpyright_summary,
    parse_pytest_results,
    process_and_save_code,
    read_local_files,
    run_basedpyright_command,
    run_pytest_command,
    run_ruff_command,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# Configure logging format and level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

HTTP_SERVICE_UNAVAILABLE = 503


@dataclass
class WorkflowContext:
    """Encapsulate context and paths for workflow execution."""

    test_file_path: str
    source_file_path: str
    prefix: str
    allow_gemini: bool


@dataclass
class GeminiRemediationContext:
    """Encapsulate all parameters needed for Gemini code remediation."""

    client: Client
    cache_name: str | None
    uploaded_files: list[types.File | None]
    config_kwargs: dict[str, object]
    output: str


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
            list[types.ContentUnion],
        ]
        | None
    ) = None


def is_syntactically_valid(code_content: str) -> bool:
    """Check if the code string is valid Python syntax."""
    try:
        ast.parse(code_content)
    except SyntaxError:
        return False
    return True


def call_gemini_with_retry(
    client: Client,
    contents_list: list[types.ContentUnion],
    config_kwargs: dict[str, object],
    prefix: str,
    spinner_msg: str,
) -> types.GenerateContentResponse:
    """Execute Gemini generate_content call with robust ServerError retry logic."""
    max_retries = 3
    response: types.GenerateContentResponse | None = None
    for attempt in range(max_retries):
        try:
            with gemini_spinner(spinner_msg, prefix):
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=contents_list,
                    config=types.GenerateContentConfig(
                        **cast("dict[str, Any]", config_kwargs),
                    ),
                )
        except ServerError as e:
            if e.code == HTTP_SERVICE_UNAVAILABLE and attempt < max_retries - 1:
                sleep_time = (2**attempt) * 2
                logger.warning(
                    "[%s] 503 Service Unavailable. Retrying in %ds (Attempt %d/%d)...",
                    prefix,
                    sleep_time,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(sleep_time)
                continue
            logger.exception(
                "[%s] Gemini Server Error persist after retries",
                prefix,
            )
            raise
        else:
            break

    if response is None:
        msg = "Failed to generate content after max retries due to server errors."
        raise RuntimeError(msg)
    return response


def _build_workflow_contents(
    ctx: WorkflowContext,
    stage: StageConfig,
    test_content: str,
    output: str,
    identical_attempts: int,
) -> list[types.ContentUnion]:
    """Build the appropriate contents list for the Gemini remediation request."""
    if stage.build_custom_contents:
        contents_list = stage.build_custom_contents(
            ctx.test_file_path,
            ctx.source_file_path,
            test_content,
            output,
        )
    else:
        contents_list = [
            types.Part.from_text(
                text=(
                    f"--- Current unit test script "
                    f"({Path(ctx.test_file_path).name}) ---\n{test_content}"
                ),
            ),
            types.Part.from_text(text=f"--- {stage.name} output ---\n{output}"),
            types.Part.from_text(
                text=(
                    f"MANDATORY INSTRUCTION: You MUST modify the code to "
                    f"resolve all {stage.name} errors. "
                    f"Do NOT return the exact same code."
                ),
            ),
        ]

    if identical_attempts > 0:
        contents_list.append(
            types.Part.from_text(
                text=(
                    "ERROR: Your previous output was IDENTICAL to the existing "
                    "file, failing to fix the error. "
                    "You are required to rewrite or update the failing test "
                    "function implementation."
                ),
            ),
        )
    return contents_list


def _process_gemini_remediation(
    ctx: WorkflowContext,
    stage: StageConfig,
    rem_ctx: GeminiRemediationContext,
) -> tuple[bool, str]:
    """Iterate with Gemini to fix test failures.

    Returns:
        tuple[bool, str]: (success, status_message)

    """
    identical_attempts = 0
    max_identical_allowed = 1

    while True:
        test_content = Path(ctx.test_file_path).read_text(encoding="utf-8")
        contents_list = _build_workflow_contents(
            ctx,
            stage,
            test_content,
            rem_ctx.output,
            identical_attempts,
        )

        response = call_gemini_with_retry(
            client=rem_ctx.client,
            contents_list=contents_list,
            config_kwargs=rem_ctx.config_kwargs,
            prefix=ctx.prefix,
            spinner_msg=f"Sending {stage.name} fix request to Gemini...",
        )

        parsed = response.parsed
        if parsed is None:
            logger.error(
                "[%s] Failed to parse Gemini response into Pydantic schema",
                ctx.prefix,
            )
            msg = "Gemini response did not conform to TestGenerationResponse schema."
            raise ValueError(msg)

        parsed_resp = cast("TestGenerationResponse", parsed)
        if not is_valid_gemini_code(parsed_resp.code) or not is_syntactically_valid(
            parsed_resp.code,
        ):
            logger.warning(
                "[%s] Gemini returned invalid/incorrect code for %s. Skipping update.",
                ctx.prefix,
                stage.name,
            )
            if CACHE_ALLOWED:
                cleanup_files(rem_ctx.client, rem_ctx.uploaded_files, ctx.prefix)
            return False, "FAILED"

        if parsed_resp.code.strip() == test_content.strip():
            if identical_attempts >= max_identical_allowed:
                logger.error(
                    "[%s] Aborting workflow stage '%s'. Gemini repeatedly returned "
                    "identical code despite warnings.\nLast error output:\n%s",
                    ctx.prefix,
                    stage.name,
                    rem_ctx.output,
                )
                if CACHE_ALLOWED:
                    cleanup_files(rem_ctx.client, rem_ctx.uploaded_files, ctx.prefix)
                return False, "No solution"

            logger.warning(
                "[%s] Gemini returned identical code to the current file. Resending "
                "request...",
                ctx.prefix,
            )
            identical_attempts += 1
            continue

        break

    if CACHE_ALLOWED:
        cleanup_files(rem_ctx.client, rem_ctx.uploaded_files, ctx.prefix)

    logger.info("[%s] Gemini response: %s", ctx.prefix, parsed_resp.message)
    process_and_save_code(parsed_resp.code, ctx.test_file_path, ctx.prefix)
    return False, "FIXED"


def run_workflow_stage(
    client: Client,
    cache_name: str | None,
    uploaded_files: list[types.File | None],
    ctx: WorkflowContext,
    stage: StageConfig,
) -> tuple[bool, str, str]:
    """Execute, evaluate, and remediate a single workflow stage.

    Returns:
        tuple[bool, str, str]: (success, stage_name, status_message)

    """
    logger.info("[%s] Running %s stage...", ctx.prefix, stage.name)
    output = stage.run_command()

    if stage.is_success(output):
        logger.info("[%s] %s passed cleanly.", ctx.prefix, stage.name)
        return True, stage.name, "SUCCESS"

    if not ctx.allow_gemini:
        logger.warning(
            "[%s] %s failed after all LLM authorized calls.",
            ctx.prefix,
            stage.name,
        )
        return False, stage.name, "FAILED"

    logger.info(
        "[%s] Reason for Gemini call: %s issues detected.",
        ctx.prefix,
        stage.name,
    )
    system_instruction_text = load_skill(stage.skill_filename)

    config_kwargs: dict[str, object] = {
        "thinking_config": types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.MEDIUM,
        ),
        "response_mime_type": "application/json",
        "response_schema": TestGenerationResponse,
        "tools": None,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(
            disable=True,
        ),
    }

    if CACHE_ALLOWED and cache_name is not None:
        config_kwargs["cached_content"] = cache_name
    else:
        config_kwargs["system_instruction"] = system_instruction_text

    rem_ctx = GeminiRemediationContext(
        client=client,
        cache_name=cache_name,
        uploaded_files=uploaded_files,
        config_kwargs=config_kwargs,
        output=output,
    )

    success, status = _process_gemini_remediation(ctx, stage, rem_ctx)
    return success, stage.name, status


def _setup_cache(
    client: Client,
    source_file_path: str,
    prefix: str,
) -> tuple[str | None, list[types.File | None]]:
    """Set up optional Gemini file caching."""
    uploaded_files: list[types.File | None] = []
    if not CACHE_ALLOWED:
        return None, uploaded_files

    logger.info("[%s] Caching enabled. Uploading static reference files...", prefix)
    file_config = upload_static_file(client, "project.toml", prefix)
    file_conftest = upload_static_file(client, "tests/conftest.py", prefix)
    file_source = upload_static_file(client, source_file_path, prefix)
    uploaded_files.extend([file_config, file_conftest, file_source])

    config_uri, conftest_uri, source_uri = validate_file_uris(
        file_config,
        file_conftest,
        file_source,
    )

    logger.info("[%s] Creating context cache...", prefix)
    cached_content = client.caches.create(
        model=MODEL_NAME,
        config=types.CreateCachedContentConfig(
            display_name=f"unit-test-context-{prefix}",
            ttl="3600s",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=source_uri,
                            mime_type="text/plain",
                        ),
                        types.Part.from_uri(
                            file_uri=config_uri,
                            mime_type="text/plain",
                        ),
                        types.Part.from_uri(
                            file_uri=conftest_uri,
                            mime_type="text/plain",
                        ),
                    ],
                ),
            ],
            system_instruction=load_skill("unit_test_generation.md"),
        ),
    )
    return cached_content.name, uploaded_files


def _run_pytest_stage(
    client: Client,
    cache_name: str | None,
    uploaded_files: list[types.File | None],
    ctx: WorkflowContext,
) -> tuple[bool, str, str]:
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
            "[%s] Pytest check evaluation | Summary: '%s' | 100%% Coverage: %s | Missing: %s | Tests Passed: %s | Syntax Error: %s",
            ctx.prefix,
            summary,
            is_100_percent,
            missing_lines,
            tests_passed,
            is_syntax_error,
        )
        if is_syntax_error:
            logger.error(
                "[%s] Syntax/Collection error details:\n%s", ctx.prefix, syntax_details
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
    ) -> list[types.ContentUnion]:
        _, _, _, _, is_syntax_error, syntax_error_details = parse_pytest_results(
            py_out,
            s_path,
        )
        if is_syntax_error:
            return [
                types.Part.from_text(
                    text=(
                        f"--- Current unit test script "
                        f"({Path(t_path).name}) ---\n{t_content}"
                    ),
                ),
                types.Part.from_text(
                    text=(
                        "--- Pytest Syntax/Collection "
                        f"Error Traceback ---\n{syntax_error_details}"
                    ),
                ),
                types.Part.from_text(
                    text=(
                        "The unit test script contains a fatal Python "
                        "SyntaxError or collection issue preventing pytest. "
                        "Please fix and return complete script."
                    ),
                ),
            ]
        return build_contents_list(t_path, s_path, t_content, "", py_out)

    return run_workflow_stage(
        client,
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

    stage_name = "Pytest/Coverage"

    with Client() as client:
        try:
            cache_name, uploaded_files = _setup_cache(
                client,
                source_file_path,
                prefix,
            )

            success, stage_name, status = _run_pytest_stage(
                client,
                cache_name,
                uploaded_files,
                ctx,
            )
            if not success:
                return False, stage_name, status

            # --- STAGE 2: Basedpyright Type Checking ---
            success, stage_name, status = run_workflow_stage(
                client,
                cache_name,
                uploaded_files,
                ctx,
                StageConfig(
                    name="Basedpyright",
                    run_command=lambda: run_basedpyright_command(
                        test_file_path,
                        prefix,
                    ),
                    is_success=lambda out: (
                        "0 errors, 0 warnings, 0 notes"
                        in parse_basedpyright_summary(out)
                    ),
                    skill_filename="basedpyright_correction.md",
                ),
            )
            if not success:
                return False, stage_name, status

            # --- STAGE 3: Ruff Linting ---
            success, stage_name, status = run_workflow_stage(
                client,
                cache_name,
                uploaded_files,
                ctx,
                StageConfig(
                    name="Ruff",
                    run_command=lambda: filter_ruff_output(
                        run_ruff_command(test_file_path, prefix),
                    ),
                    is_success=lambda out: (
                        ("Ruff Status: PASSED" in out or "All checks passed!" in out)
                        and "FAILED" not in out
                        and "error" not in out.lower()
                    ),
                    skill_filename="ruff_correction.md",
                ),
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
            return False, stage_name, "API_ERROR"
        except (OSError, ValueError):
            logger.exception("[%s] File I/O or Value Error", prefix)
            raise
        except subprocess.SubprocessError:
            logger.exception("[%s] Subprocess Execution Error", prefix)
            raise
        else:
            return True, "ALL_STAGES", "SUCCESS"
