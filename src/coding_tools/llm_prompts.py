# src/coding_tools/llm_prompts.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Build prompts, load skills, and contents list."""

from __future__ import annotations

from pathlib import Path

from coding_tools import my_logger, pytest_cov
from coding_tools.config import is_caching_allowed
from coding_tools.parsers import (
    extract_pytest_errors,
    extract_pytest_warnings,
    extract_uncovered_blocks,
)

logger = my_logger.logger(__name__)


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

    analysis_section = pytest_cov.tips(source_file_path)

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
            analysis_section,
            (
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
