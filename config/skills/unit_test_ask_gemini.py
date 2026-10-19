# src/coding_tools/unit_test_ask_gemini.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Run automated test generation, coverage analysis, basedpyright, and ruff checks using Gemini API."""

from __future__ import annotations

import difflib
import logging
import subprocess
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from google.genai import Client, errors, types
from pydantic import BaseModel

if TYPE_CHECKING:
    from google.genai.types import File

# --- CONFIGURATION CONSTANTS ---
CACHE_ALLOWED: bool = False  # Set to True only if using a paid tier supporting caching
MODEL_NAME: str = "gemini-3.5-flash-lite"

# Configure logging format and level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class TestGenerationResponse(BaseModel):
    """Define the expected JSON structure returned by Gemini."""

    message: str  # Brief explanation of what was fixed or changed
    code: str  # The clean, complete unit test Python code


@contextmanager
def gemini_spinner(message: str, prefix: str = "") -> Generator[None, None, None]:
    """Context manager to print dots in the console while waiting for synchronous Gemini calls."""
    logger.info(f"[{prefix}] {message}")
    stop_event = threading.Event()

    def spin() -> None:
        while not stop_event.is_set():
            print(".", end="", flush=True)
            time.sleep(1)
        print()  # Ensure newline after dots finish

    spinner_thread = threading.Thread(target=spin, daemon=True)
    spinner_thread.start()
    try:
        yield
    finally:
        stop_event.set()
        spinner_thread.join()


def load_skill(skill_filename: str) -> str:
    """Load a specific skill from the config/skills Markdown files."""
    skill_path = Path("config/skills") / skill_filename
    return skill_path.read_text(encoding="utf-8")


def upload_static_file(client: Client, file_path: str, prefix: str) -> File:
    """Upload a static reference file to Gemini."""
    logger.info(f"[{prefix}] Uploading static reference file: {file_path}")
    return client.files.upload(
        file=file_path,
        config=types.UploadFileConfig(mime_type="text/plain"),
    )


def cleanup_files(client: Client, files: list[File | None], prefix: str) -> None:
    """Clean up uploaded remote file resources safely."""
    logger.info(f"[{prefix}] Cleaning up remote uploaded static files...")
    for f in files:
        if f is not None and f.name is not None:
            try:
                client.files.delete(name=f.name)
            except errors.APIError as e:
                logger.warning(
                    f"[{prefix}] Failed to delete remote file {f.name}: {e.message}",
                )


def validate_file_uris(
    file_config: File,
    file_conftest: File,
    file_source: File,
) -> tuple[str, str, str]:
    """Validate that uploaded file URIs are not None (satisfies TRY301)."""
    if file_config.uri is None or file_conftest.uri is None or file_source.uri is None:
        msg = "One or more uploaded file URIs resolved to None."
        raise ValueError(msg)
    return file_config.uri, file_conftest.uri, file_source.uri


def run_pytest_command(test_file_path: str, source_file_path: str, prefix: str) -> None:
    """Execute the pytest command and save command + output to a unique test log."""
    test_stem = Path(test_file_path).stem

    # Robust, OS-agnostic module path conversion (handles both / and \ slashes)
    source_path = Path(source_file_path)
    try:
        relative_source = source_path.relative_to("src")
    except ValueError:
        relative_source = source_path
    module_path = ".".join(relative_source.with_suffix("").parts)

    cmd_list = [
        "uv",
        "run",
        "pytest",
        "--import-mode=importlib",
        f"--cov={module_path}",
        "--cov-report=term-missing",
        "--cov-report=annotate",
        test_file_path,
    ]
    cmd_str = " ".join(cmd_list)
    logger.info(f"[{prefix}] Running command: {cmd_str}")

    result = subprocess.run(
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    output_path = Path(f"unit-test-{test_stem}.txt")
    full_content = f"$ {cmd_str}\n\n{result.stdout}\n{result.stderr}"
    output_path.write_text(full_content, encoding="utf-8")


def run_basedpyright_command(test_file_path: str, prefix: str) -> str:
    """Execute basedpyright and save command + output to a unique pyright log."""
    test_stem = Path(test_file_path).stem
    cmd_list = [
        "uv",
        "run",
        "basedpyright",
        test_file_path,
    ]
    cmd_str = " ".join(cmd_list)
    logger.info(f"[{prefix}] Running command: {cmd_str}")

    result = subprocess.run(
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    output_path = Path(f"based-pyright-{test_stem}.txt")
    full_content = f"$ {cmd_str}\n\n{result.stdout}\n{result.stderr}"
    output_path.write_text(full_content, encoding="utf-8")
    return full_content


def run_ruff_command(test_file_path: str, prefix: str) -> str:
    """Execute ruff check with --fix and save command + output to a unique ruff log."""
    test_stem = Path(test_file_path).stem
    cmd_list = [
        "uv",
        "run",
        "ruff",
        "check",
        test_file_path,
        "--fix",
    ]
    cmd_str = " ".join(cmd_list)
    logger.info(f"[{prefix}] Running command: {cmd_str}")

    result = subprocess.run(
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    output_path = Path(f"ruff-{test_stem}.txt")
    full_content = f"$ {cmd_str}\n\n{result.stdout}\n{result.stderr}"
    output_path.write_text(full_content, encoding="utf-8")
    return full_content


def parse_pytest_results(output_text: str) -> tuple[str, str, bool, bool]:
    """Extract pytest summary, missing lines, and check if tests passed cleanly with 100% coverage."""
    summary = "No summary found"
    for line in reversed(output_text.splitlines()):
        stripped = line.strip()
        if any(
            kw in stripped
            for kw in ["passed", "failed", "error", "skipped", "no tests ran"]
        ):
            summary = stripped
            break

    summary_lower = summary.lower()
    tests_passed = "failed" not in summary_lower and "error" not in summary_lower

    missing_lines = "None"
    is_100_percent = False
    in_coverage_section = False

    for line in output_text.splitlines():
        if "tests coverage" in line:
            in_coverage_section = True
            continue
        if in_coverage_section and ".py" in line and "TOTAL" not in line:
            parts = line.split()
            if len(parts) >= 3 and parts[2].isdigit():
                miss_count = int(parts[2])
                cover_str = parts[3] if len(parts) > 3 else ""
                if miss_count == 0 or cover_str == "100%":
                    is_100_percent = True
                    missing_lines = "None (100% coverage)"
                else:
                    is_100_percent = False
                    missing_lines = (
                        " ".join(parts[4:])
                        if len(parts) > 4
                        else f"Missing lines (Miss count: {miss_count})"
                    )
                break

    return summary, missing_lines, tests_passed, is_100_percent


def extract_pytest_warnings(pytest_output: str) -> str:
    """Extract pytest warnings from the warnings summary section."""
    lines = pytest_output.splitlines()
    warning_lines: list[str] = []
    capturing = False
    for line in lines:
        if "warnings summary" in line.lower():
            capturing = True
            continue
        if capturing:
            if "-- Docs:" in line or "tests coverage" in line:
                break
            warning_lines.append(line)
    cleaned = "\n".join(warning_lines).strip()
    return cleaned or "None"


def parse_basedpyright_summary(output_text: str) -> str:
    """Extract the final summary line from basedpyright output."""
    for line in reversed(output_text.splitlines()):
        stripped = line.strip()
        if "error" in stripped or "warning" in stripped or "note" in stripped:
            return stripped
    return "No summary found"


def parse_ruff_summary(output_text: str) -> str:
    """Extract the summary line from ruff output ('All checks passed!' or 'Found X error(s).')."""
    for line in output_text.splitlines():
        stripped = line.strip()
        if "All checks passed!" in stripped or (
            "Found " in stripped and "error" in stripped
        ):
            return stripped
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    return lines[-1] if lines else "No summary found"


def filter_ruff_output(output_text: str) -> str:
    """Remove config incompatibility warning lines from ruff output before sending to Gemini."""
    filtered_lines = [
        line
        for line in output_text.splitlines()
        if not line.strip().lower().startswith("warning:")
    ]
    return "\n".join(filtered_lines)


def extract_uncovered_blocks(coverage_text: str) -> list[str]:
    """Extract the first line of each contiguous block of uncovered lines (!) from coverage."""
    lines = coverage_text.splitlines()
    uncovered_snippets: list[str] = []
    in_block = False
    current_block_first_line = ""

    for line in lines:
        if line.lstrip().startswith("!"):
            if not in_block:
                in_block = True
                current_block_first_line = line
        elif in_block:
            in_block = False
            if current_block_first_line:
                uncovered_snippets.append(current_block_first_line)

    if in_block and current_block_first_line:
        uncovered_snippets.append(current_block_first_line)

    return uncovered_snippets


def read_local_files(
    test_file_path: str,
    source_file_path: str,
    prefix: str,
) -> tuple[str, str, str]:
    """Read local dynamic test, coverage, and log files safely using Path."""
    logger.info(
        f"[{prefix}] Reading local dynamic test, coverage, and log files for Gemini payload...",
    )
    test_stem = Path(test_file_path).stem

    test_content = Path(test_file_path).read_text(encoding="utf-8")

    cover_path = Path(f"{source_file_path},cover")
    if cover_path.exists():
        coverage_content = cover_path.read_text(encoding="utf-8")
    else:
        coverage_content = (
            "No coverage report generated due to pytest collection or execution error."
        )

    pytest_output = Path(f"unit-test-{test_stem}.txt").read_text(encoding="utf-8")

    return test_content, coverage_content, pytest_output


def build_contents_list(
    test_file_path: str,
    source_file_path: str,
    test_content: str,
    coverage_content: str,
    pytest_output: str,
) -> list[types.ContentUnion]:
    """Build the dynamic contents list for the Gemini model request."""
    contents_list: list[types.ContentUnion] = []

    if not CACHE_ALLOWED:
        toml_content = Path("pyproject.toml").read_text(encoding="utf-8")
        conftest_content = Path("tests/conftest.py").read_text(encoding="utf-8")
        source_content = Path(source_file_path).read_text(encoding="utf-8")

        contents_list.extend(
            [
                types.Part.from_text(text=f"--- pyproject.toml ---\n{toml_content}"),
                types.Part.from_text(
                    text=f"--- tests/conftest.py ---\n{conftest_content}",
                ),
                types.Part.from_text(
                    text=(f"--- {source_file_path} ---\n{source_content}"),
                ),
            ],
        )

    uncovered_blocks = extract_uncovered_blocks(coverage_content)
    uncovered_summary = (
        "\n".join([f"- starting by {line}" for line in uncovered_blocks])
        if uncovered_blocks
        else "None"
    )

    pytest_warnings = extract_pytest_warnings(pytest_output)
    test_filename = Path(test_file_path).name

    contents_list.extend(
        [
            types.Part.from_text(
                text=(
                    "--- Current unit test script "
                    f"({test_filename}) ---\n{test_content}"
                ),
            ),
            types.Part.from_text(
                text=(
                    "--- Uncovered Code Blocks Summary ---\n"
                    "The following code blocks are not or only partly covered:\n"
                    f"{uncovered_summary}\n\n"
                    "--- Coverage report (! marks uncovered lines) ---\n"
                    f"{coverage_content}"
                ),
            ),
            types.Part.from_text(
                text=(
                    "--- Pytest Warnings Summary ---\n"
                    f"{pytest_warnings}\n\n"
                    "Address these specific warnings if possible."
                ),
            ),
            types.Part.from_text(text=f"--- Pytest output ---\n{pytest_output}"),
            types.Part.from_text(
                text="Analyze these, fix any failures, warnings, or collection/import errors, and ensure tests pass with 100% coverage.",
            ),
        ],
    )
    return contents_list


def is_valid_gemini_code(code: str) -> bool:
    """Validate that Gemini returned actual code (>5 lines and contains a comment tag starting with #)."""
    lines = [line for line in code.splitlines() if line.strip()]
    if len(lines) <= 5:
        return False
    return any(line.strip().startswith("#") for line in lines)


def process_and_save_code(new_code: str, test_file_path: str, prefix: str) -> None:
    """Calculate diff statistics, log diff as debug, and save new test code."""
    test_path = Path(test_file_path)
    old_code = test_path.read_text(encoding="utf-8")

    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)

    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{test_file_path}",
            tofile=f"b/{test_file_path}",
        ),
    )
    if diff:
        logger.info(f"[{prefix}] Code Diff:\n" + "".join(diff))

    test_path.write_text(new_code, encoding="utf-8")
    logger.info(f"[{prefix}] Saved updated test script to {test_path}")


def execute_workflow(
    test_file_path: str = "tests/unit/test_workspace_stamper.py",
    source_file_path: str = "src/coding_tools/workspace_stamper.py",
    allow_gemini: bool = True,
) -> tuple[bool, str]:
    """Execute the automated test generation, type checking, and linting workflow.

    Returns:
        tuple[bool, str]: (success: bool, status: str)

    """
    prefix = Path(test_file_path).name
    uploaded_files: list[File | None] = []
    cache_name: str | None = None

    with Client() as client:
        try:
            if CACHE_ALLOWED and allow_gemini:
                logger.info(
                    f"[{prefix}] Caching is enabled. Uploading static reference files...",
                )
                file_config = upload_static_file(client, "project.toml", prefix)
                file_conftest = upload_static_file(client, "tests/conftest.py", prefix)
                file_source = upload_static_file(client, source_file_path, prefix)
                uploaded_files.extend([file_config, file_conftest, file_source])

                config_uri, conftest_uri, source_uri = validate_file_uris(
                    file_config,
                    file_conftest,
                    file_source,
                )

                logger.info(f"[{prefix}] Creating context cache...")
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
                cache_name = cached_content.name

            # --- STAGE 1: Pytest & Coverage Workflow ---
            run_pytest_command(test_file_path, source_file_path, prefix)
            test_content, coverage_content, pytest_output = read_local_files(
                test_file_path,
                source_file_path,
                prefix,
            )

            summary, missing_lines, tests_passed, is_100_percent = parse_pytest_results(
                pytest_output,
            )
            logger.info(f"[{prefix}] Test results summary: {summary}")
            logger.info(f"[{prefix}] Uncovered lines: {missing_lines}")

            summary_lower = summary.lower()
            has_error = "error" in summary_lower or "error" in pytest_output.lower()
            has_failure = "failed" in summary_lower
            pytest_warnings = extract_pytest_warnings(pytest_output)
            has_warning = pytest_warnings != "None"

            if has_error:
                pytest_status = "ERROR"
            elif has_failure:
                pytest_status = "FAILURE"
            elif not is_100_percent:
                pytest_status = "MISSING_COVERAGE"
            elif has_warning:
                pytest_status = "WARNING"
            else:
                pytest_status = "OK"

            if pytest_status != "OK":
                if not allow_gemini:
                    return False, pytest_status

                logger.info(
                    f"[{prefix}] Reason for Gemini call: Pytest status is {pytest_status}.",
                )
                system_instruction_text = load_skill("unit_test_generation.md")
                contents_list = build_contents_list(
                    test_file_path,
                    source_file_path,
                    test_content,
                    coverage_content,
                    pytest_output,
                )

                config_kwargs: dict[str, Any] = {
                    "thinking_config": types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.MINIMAL,
                    ),
                    "response_mime_type": "application/json",
                    "response_schema": TestGenerationResponse,
                }
                if CACHE_ALLOWED and cache_name is not None:
                    config_kwargs["cached_content"] = cache_name
                else:
                    config_kwargs["system_instruction"] = system_instruction_text

                with gemini_spinner("Sending generation request to Gemini...", prefix):
                    response = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=contents_list,
                        config=types.GenerateContentConfig(**config_kwargs),
                    )

                if CACHE_ALLOWED:
                    cleanup_files(client, uploaded_files, prefix)

                parsed = response.parsed
                if parsed is None:
                    logger.error(
                        f"[{prefix}] Failed to parse Gemini response into Pydantic schema.",
                    )
                    raise ValueError(
                        "Gemini response did not conform to TestGenerationResponse schema.",
                    )

                parsed_resp = cast("TestGenerationResponse", parsed)
                if not is_valid_gemini_code(parsed_resp.code):
                    logger.warning(
                        f"[{prefix}] Gemini returned invalid/insufficient code. Skipping update.",
                    )
                    return False, pytest_status

                logger.info(f"[{prefix}] Gemini response: {parsed_resp.message}")
                process_and_save_code(parsed_resp.code, test_file_path, prefix)
                return False, "FIXED"

            # --- STAGE 2: Basedpyright Type Checking Workflow ---
            logger.info(f"[{prefix}] Tests & coverage passed. Running basedpyright...")
            basedpyright_output = run_basedpyright_command(test_file_path, prefix)
            bp_summary = parse_basedpyright_summary(basedpyright_output)
            logger.info(f"[{prefix}] Basedpyright summary: {bp_summary}")

            if "0 errors, 0 warnings, 0 notes" not in bp_summary:
                if not allow_gemini:
                    return False, "BASEDPYRIGHT"

                logger.info(
                    f"[{prefix}] Reason for Gemini call: Basedpyright issues found ({bp_summary}).",
                )
                system_instruction_text = load_skill("basedpyright_correction.md")

                # RE-READ latest test content from disk to avoid stale snapshot
                logger.info(
                    f"[{prefix}] Reading latest test content from disk for Basedpyright Gemini call...",
                )
                test_content = Path(test_file_path).read_text(encoding="utf-8")

                bp_contents_list: list[types.ContentUnion] = [
                    types.Part.from_text(
                        text=f"--- Current unit test script ({Path(test_file_path).name}) ---\n{test_content}",
                    ),
                    types.Part.from_text(
                        text=f"--- Basedpyright output ---\n{basedpyright_output}",
                    ),
                    types.Part.from_text(
                        text="Please resolve all Basedpyright type-checking errors in the unit test script.",
                    ),
                ]

                with gemini_spinner(
                    "Sending Basedpyright fix request to Gemini...",
                    prefix,
                ):
                    response = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=bp_contents_list,
                        config=types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(
                                thinking_level=types.ThinkingLevel.MINIMAL,
                            ),
                            response_mime_type="application/json",
                            response_schema=TestGenerationResponse,
                            system_instruction=system_instruction_text,
                        ),
                    )

                if CACHE_ALLOWED:
                    cleanup_files(client, uploaded_files, prefix)

                parsed_bp = response.parsed
                if parsed_bp is None:
                    logger.error(
                        f"[{prefix}] Failed to parse Gemini response into Pydantic schema.",
                    )
                    raise ValueError(
                        "Gemini response did not conform to TestGenerationResponse schema.",
                    )

                parsed_bp_resp = cast("TestGenerationResponse", parsed_bp)
                if not is_valid_gemini_code(parsed_bp_resp.code):
                    logger.warning(
                        f"[{prefix}] Gemini returned invalid/insufficient code. Skipping update.",
                    )
                    return False, "BASEDPYRIGHT"

                logger.info(f"[{prefix}] Gemini response: {parsed_bp_resp.message}")
                process_and_save_code(parsed_bp_resp.code, test_file_path, prefix)
                return False, "FIXED"

            # --- STAGE 3: Ruff Linting Workflow ---
            logger.info(f"[{prefix}] Basedpyright passed. Running ruff check...")
            ruff_output = run_ruff_command(test_file_path, prefix)
            ruff_summary = parse_ruff_summary(ruff_output)
            logger.info(f"[{prefix}] Ruff summary: {ruff_summary}")

            if "All checks passed!" in ruff_output:
                logger.info(
                    f"[{prefix}] Success! Pytest, Basedpyright, and Ruff checks passed cleanly.",
                )
                if CACHE_ALLOWED:
                    cleanup_files(client, uploaded_files, prefix)
                return True, "SUCCESS"

            if not allow_gemini:
                return False, "RUFF"

            logger.info(
                f"[{prefix}] Reason for Gemini call: Ruff issues found ({ruff_summary}).",
            )
            system_instruction_text = load_skill("ruff_correction.md")
            cleaned_ruff_output = filter_ruff_output(ruff_output)

            # RE-READ latest test content from disk to avoid stale snapshot
            logger.info(
                f"[{prefix}] Reading latest test content from disk for Ruff Gemini call...",
            )
            test_content = Path(test_file_path).read_text(encoding="utf-8")

            ruff_contents_list: list[types.ContentUnion] = [
                types.Part.from_text(
                    text=f"--- Current unit test script ({Path(test_file_path).name}) ---\n{test_content}",
                ),
                types.Part.from_text(
                    text=f"--- Ruff output ---\n{cleaned_ruff_output}",
                ),
                types.Part.from_text(
                    text="Please resolve all Ruff linting errors and warnings in the unit test script.",
                ),
            ]

            with gemini_spinner("Sending Ruff fix request to Gemini...", prefix):
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=ruff_contents_list,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(
                            thinking_level=types.ThinkingLevel.MINIMAL,
                        ),
                        response_mime_type="application/json",
                        response_schema=TestGenerationResponse,
                        system_instruction=system_instruction_text,
                    ),
                )

            if CACHE_ALLOWED:
                cleanup_files(client, uploaded_files, prefix)

            parsed_ruff = response.parsed
            if parsed_ruff is None:
                logger.error(
                    f"[{prefix}] Failed to parse Gemini response into Pydantic schema.",
                )
                raise ValueError(
                    "Gemini response did not conform to TestGenerationResponse schema.",
                )

            parsed_ruff_resp = cast("TestGenerationResponse", parsed_ruff)
            if not is_valid_gemini_code(parsed_ruff_resp.code):
                logger.warning(
                    f"[{prefix}] Gemini returned invalid/insufficient code. Skipping update.",
                )
                return False, "RUFF"

            logger.info(f"[{prefix}] Gemini response: {parsed_ruff_resp.message}")
            process_and_save_code(parsed_ruff_resp.code, test_file_path, prefix)
            return False, "FIXED"

        except errors.APIError as e:
            logger.exception(f"[{prefix}] Gemini API Error (Code {e.code})")
            raise
        except (OSError, ValueError):
            logger.exception(f"[{prefix}] File I/O or Value Error")
            raise
        except subprocess.SubprocessError:
            logger.exception(f"[{prefix}] Subprocess Execution Error")
            raise
