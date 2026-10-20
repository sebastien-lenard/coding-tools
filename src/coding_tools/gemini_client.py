# src/coding_tools/gemini_client.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Google GenAI client wrapper satisfying LLMClientProtocol."""

from __future__ import annotations

import logging
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

from google.genai import Client, errors, types
from google.genai.errors import ServerError
from pydantic import BaseModel

from coding_tools.config import get_provider_mapping, is_caching_allowed
from coding_tools.llm_prompts import load_skill
from coding_tools.parsers import (
    extract_pytest_errors,
    extract_pytest_warnings,
    extract_uncovered_blocks,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from google.genai.types import File

    from coding_tools.llm_protocol import StructuredGenerationOptions

HTTP_SERVICE_UNAVAILABLE = 503

T = TypeVar("T", bound=BaseModel)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class RetryRequestParameters:
    """Encapsulates parameters for Gemini API execution attempts."""

    client: Client
    model_name: str
    contents_list: list[types.ContentUnion]
    config_kwargs: dict[str, object]
    prefix: str
    spinner_msg: str


@contextmanager
def gemini_spinner(message: str, prefix: str = "") -> Generator[None, None, None]:
    """Context manager to print inline dots in console while waiting for calls."""
    logger.info("[%s] %s (waiting)", prefix, message)
    stop_event = threading.Event()

    def spin() -> None:
        while not stop_event.is_set():
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(1)

    spinner_thread = threading.Thread(target=spin, daemon=True)
    spinner_thread.start()
    try:
        yield
    finally:
        stop_event.set()
        spinner_thread.join()
        sys.stdout.write("\n")
        sys.stdout.flush()


def upload_static_file(client: Client, file_path: str, prefix: str) -> File:
    """Upload a static reference file to Gemini."""
    logger.info("[%s] Uploading static reference file: %s", prefix, file_path)
    return client.files.upload(
        file=file_path,
        config=types.UploadFileConfig(mime_type="text/plain"),
    )


def validate_file_uris(
    file_config: File,
    file_conftest: File,
    file_source: File,
) -> tuple[str, str, str]:
    """Validate that uploaded file URIs are not None."""
    if file_config.uri is None or file_conftest.uri is None or file_source.uri is None:
        msg = "One or more uploaded file URIs resolved to None."
        raise ValueError(msg)
    return file_config.uri, file_conftest.uri, file_source.uri


def build_config(
    response_schema: type[BaseModel],
    system_instruction: str | None = None,
    cache_name: str | None = None,
) -> dict[str, object]:
    """Centralized configuration factory for structured GenAI execution."""
    config_kwargs: dict[str, object] = {
        "thinking_config": types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.MEDIUM,
        ),
        "response_mime_type": "application/json",
        "response_schema": response_schema,
        "tools": None,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(
            disable=True,
        ),
    }

    if is_caching_allowed("gemini") and cache_name is not None:
        config_kwargs["cached_content"] = cache_name
    elif system_instruction is not None:
        config_kwargs["system_instruction"] = system_instruction

    return config_kwargs


def call_gemini_with_retry(
    params: RetryRequestParameters,
) -> types.GenerateContentResponse:
    """Execute Gemini generate_content call with robust ServerError retry logic."""
    max_retries = 3
    response: types.GenerateContentResponse | None = None
    for attempt in range(max_retries):
        try:
            with gemini_spinner(params.spinner_msg, params.prefix):
                response = params.client.models.generate_content(
                    model=params.model_name,
                    contents=params.contents_list,
                    config=types.GenerateContentConfig(
                        **dict[str, Any](params.config_kwargs),
                    ),
                )
        except ServerError as e:
            if e.code == HTTP_SERVICE_UNAVAILABLE and attempt < max_retries - 1:
                sleep_time = (2**attempt) * 2
                logger.warning(
                    "[%s] 503 Service Unavailable. Retrying in %ds (Attempt %d/%d)...",
                    params.prefix,
                    sleep_time,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(sleep_time)
                continue
            logger.exception(
                "[%s] Gemini Server Error persist after retries",
                params.prefix,
            )
            raise
        else:
            break

    if response is None:
        msg = "Failed to generate content after max retries due to server errors."
        raise RuntimeError(msg)
    return response


class GeminiClientAdapter:
    """Concrete Gemini adapter satisfying LLMClientProtocol."""

    def __init__(self, model_name: str | None = None) -> None:
        self.client = Client()
        if model_name is not None:
            self.model_name = model_name
        else:
            providers = get_provider_mapping()
            gemini_config = providers.get("gemini", {})
            self.model_name = str(
                gemini_config.get("default_model", "gemini-3.5-flash-lite"),
            )

    @property
    def supports_caching(self) -> bool:
        """Return whether caching is enabled and supported for gemini."""
        return is_caching_allowed("gemini")

    def generate_structured_response(
        self,
        contents_list: list[object],
        options: StructuredGenerationOptions,
    ) -> BaseModel:
        """High-level wrapper returning a validated Pydantic model response."""
        config_kwargs = build_config(
            response_schema=options.response_schema,
            system_instruction=options.system_instruction,
            cache_name=options.cache_name,
        )

        # Translate agnostic text contents into Gemini Part objects
        gemini_contents: list[types.ContentUnion] = [
            types.Part.from_text(text=str(item)) for item in contents_list
        ]

        params = RetryRequestParameters(
            client=self.client,
            model_name=self.model_name,
            contents_list=gemini_contents,
            config_kwargs=config_kwargs,
            prefix=options.prefix,
            spinner_msg=options.spinner_msg,
        )

        response = call_gemini_with_retry(params)

        parsed = response.parsed
        if parsed is None:
            schema_name = options.response_schema.__name__
            msg = f"GenAI response did not conform to {schema_name} schema."
            raise ValueError(msg)

        return options.response_schema.model_validate(parsed)

    def setup_cache(
        self,
        source_file_path: str,
        prefix: str,
    ) -> tuple[str | None, list[object]]:
        """Set up optional Gemini file caching."""
        uploaded_files: list[File | None] = []
        if not self.supports_caching:
            return None, uploaded_files  # type: ignore[return-value]

        logger.info("[%s] Caching enabled. Uploading static reference files...", prefix)
        file_config = upload_static_file(self.client, "project.toml", prefix)
        file_conftest = upload_static_file(self.client, "tests/conftest.py", prefix)
        file_source = upload_static_file(self.client, source_file_path, prefix)
        uploaded_files.extend([file_config, file_conftest, file_source])

        config_uri, conftest_uri, source_uri = validate_file_uris(
            file_config,
            file_conftest,
            file_source,
        )

        logger.info("[%s] Creating context cache...", prefix)
        cached_content = self.client.caches.create(
            model=self.model_name,
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
        return cached_content.name, uploaded_files  # type: ignore[return-value]

    def cleanup_files(self, files: list[object], prefix: str) -> None:
        """Clean up remote uploaded static files safely."""
        logger.info("[%s] Cleaning up remote uploaded static files...", prefix)
        for f in files:
            if f is not None and hasattr(f, "name"):
                try:
                    file_name = cast("Any", f).name
                    self.client.files.delete(name=file_name)
                except errors.APIError as e:
                    logger.warning(
                        "[%s] Failed to delete remote file: %s",
                        prefix,
                        e.message,
                    )


def generate_coverage_hints(source_file_path: str) -> list[str]:
    """Inspect uncovered/partial lines and build precise instructions."""
    cover_path = Path(f"{source_file_path},cover")
    if not cover_path.exists():
        return []

    source_path = Path(source_file_path)
    if not source_path.exists():
        return []

    source_lines = source_path.read_text(encoding="utf-8").splitlines()
    cover_lines = cover_path.read_text(encoding="utf-8").splitlines()

    hints = []
    for idx, cover_line in enumerate(cover_lines):
        if cover_line.startswith(("!", ">")):
            if idx >= len(source_lines):
                continue

            actual_code = source_lines[idx].strip()

            if " and " in actual_code or " or " in actual_code:
                hints.append(
                    f"GENERIC HINT (Line {idx + 1}): The compound boolean "
                    f"expression `{actual_code}` was not fully covered. Ensure "
                    "you write test cases where each side evaluates to "
                    "both True and False independently,",
                )
            elif actual_code.startswith("if "):
                hints.append(
                    f"GENERIC HINT (Line {idx + 1}): The conditional block "
                    f"`{actual_code}` was never entered or its branch was "
                    "missed. Provide a test input that forces this "
                    "condition to evaluate to True,",
                )
            elif actual_code.startswith("except "):
                hints.append(
                    f"GENERIC HINT (Line {idx + 1}): The exception handler "
                    f"`{actual_code}` was never triggered. Write a test case "
                    "that raises this specific exception,",
                )

    return hints


def build_contents_list(
    test_file_path: str,
    source_file_path: str,
    test_content: str,
    coverage_content: str,
    pytest_output: str,
) -> list[str]:
    """Build the dynamic contents list as agnostic plain strings."""
    contents_list: list[str] = []

    if not is_caching_allowed("gemini"):
        toml_content = Path("pyproject.toml").read_text(encoding="utf-8")
        conftest_content = Path("tests/conftest.py").read_text(encoding="utf-8")
        source_content = Path(source_file_path).read_text(encoding="utf-8")

        contents_list.extend(
            [
                f"--- pyproject.toml ---\n{toml_content}",
                f"--- tests/conftest.py ---\n{conftest_content}",
                f"--- {source_file_path} ---\n{source_content}",
            ],
        )

    uncovered_blocks = extract_uncovered_blocks(coverage_content)
    uncovered_summary = (
        "\n".join([f"- starting by {line}" for line in uncovered_blocks])
        if uncovered_blocks
        else "None"
    )

    generic_hints = generate_coverage_hints(source_file_path)
    hints_summary = (
        "\n".join([f"- {hint}" for hint in generic_hints])
        if generic_hints
        else "None identified."
    )

    pytest_errors = extract_pytest_errors(pytest_output)
    pytest_warnings = extract_pytest_warnings(pytest_output)
    test_filename = Path(test_file_path).name

    contents_list.extend(
        [
            f"--- Current unit test script ({test_filename}) ---\n{test_content}",
            (
                "--- Pytest Assertion/Execution Errors (HIGHEST PRIORITY) ---\n"
                f"{pytest_errors}\n\n"
                "You MUST fix these assertion or execution failures first."
            ),
            (
                "--- Programmatic Branch & Coverage Analysis ---\n"
                f"{hints_summary}\n\n"
                "--- Uncovered Code Blocks Summary ---\n"
                "The following code blocks are not or only partly covered:\n"
                f"{uncovered_summary}\n\n"
                "--- Coverage report (! marks uncovered lines) ---\n"
                f"{coverage_content}"
            ),
            (
                "--- Pytest Warnings Summary ---\n"
                f"{pytest_warnings}\n\n"
                "Address these specific warnings if possible."
            ),
            f"--- Pytest output ---\n{pytest_output}",
            (
                "Analyze these, fix any failures, warnings, or collection/import "
                "errors, and ensure tests pass with 100% coverage."
            ),
        ],
    )
    return contents_list
