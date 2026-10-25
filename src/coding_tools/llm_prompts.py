# src/coding_tools/llm_prompts.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Build prompts, load skills, and contents list."""

from __future__ import annotations

from pathlib import Path

from coding_tools.config import is_caching_allowed
from coding_tools.logger import get_project_logger
from coding_tools.parsers import (
    extract_pytest_errors,
    extract_pytest_warnings,
    extract_uncovered_blocks,
)

logger = get_project_logger(__name__)


def load_skill(skill_filename: str) -> str:
    """Read skill markdown from config/skills.

    Raise FileNotFoundError if missing.
    """
    skill_path = Path("config/skills") / skill_filename
    try:
        return skill_path.read_text(encoding="utf-8")
    except OSError:
        logger.exception(skill_path, "Failed to load skill file")
        raise


def generate_coverage_hints(source_file_path: str) -> list[str]:
    """Yield hints for uncovered lines from source and .cover files.

    Return empty list if files missing.
    """
    cover_path = Path(f"{source_file_path},cover")
    if not cover_path.exists():
        return []

    source_path = Path(source_file_path)
    if not source_path.exists():
        return []

    try:
        source_lines = source_path.read_text(encoding="utf-8").splitlines()
        cover_lines = cover_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.exception(source_path, "Failed to read source or cover file for hints")
        return []

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
    """Build contents list with source, tests, coverage, and pytest logs.

    Add pyproject.toml and conftest.py if no caching.
    """
    contents_list: list[str] = []

    if not is_caching_allowed("gemini"):
        try:
            toml_content = Path("pyproject.toml").read_text(encoding="utf-8")
            conftest_content = Path("tests/conftest.py").read_text(encoding="utf-8")
            source_content = Path(source_file_path).read_text(encoding="utf-8")
        except OSError:
            logger.exception(
                source_file_path,
                "Failed to read project setup files for contents",
            )
            raise

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
