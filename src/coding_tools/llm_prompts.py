# src/coding_tools/llm_prompts.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Prompt, skill loader, and agnostic content builder utilities."""

from __future__ import annotations

from pathlib import Path

from coding_tools.config import is_caching_allowed
from coding_tools.parsers import (
    extract_pytest_errors,
    extract_pytest_warnings,
    extract_uncovered_blocks,
)


def load_skill(skill_filename: str) -> str:
    """Load a specific skill from the config/skills Markdown files."""
    skill_path = Path("config/skills") / skill_filename
    return skill_path.read_text(encoding="utf-8")


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
