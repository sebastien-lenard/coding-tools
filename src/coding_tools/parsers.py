# src/coding_tools/parsers.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Local file parsers, test/lint commands, diffing, and code validation utilities."""

from __future__ import annotations

import ast
import difflib
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Constants to replace magic numbers
MIN_PARTS_FOR_COVERAGE = 3
MIN_PARTS_WITH_MISSING = 4
MAX_BACKWARD_LOOKUP = 5
MIN_LINES_FOR_GEMINI_CODE = 5


def run_pytest_command(
    test_file_path: str,
    source_file_path: str,
    prefix: str,
) -> None:
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
    logger.info("[%s] Running command: %s", prefix, cmd_str)

    result = subprocess.run(  # noqa: S603
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
    logger.info("[%s] Running command: %s", prefix, cmd_str)

    result = subprocess.run(  # noqa: S603
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
    logger.info("[%s] Running command: %s", prefix, cmd_str)

    result = subprocess.run(  # noqa: S603
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    # Extract the actual summary line from ruff output for clear logging
    summary_line = "All checks passed!"
    for line in result.stdout.splitlines():
        if "Found " in line or "All checks passed!" in line:
            summary_line = line.strip()
            break
    if result.returncode != 0 and "Found " not in result.stdout:
        summary_line = f"Ruff failed with exit code {result.returncode}"

    logger.info("[%s] Ruff Execution Result: %s", prefix, summary_line)

    output_path = Path(f"ruff-{test_stem}.txt")
    full_content = (
        f"$ {cmd_str}\n\nRuff Summary: {summary_line}\n\n"
        f"{result.stdout}\n{result.stderr}"
    )
    output_path.write_text(full_content, encoding="utf-8")
    return full_content


def parse_pytest_results(
    output_text: str,
    source_file_path: str | None = None,
) -> tuple[str, str, bool, bool, bool, str]:
    """Extract test/coverage, syntax error flag, and traceback for the specific source file."""
    summary = "No summary found"
    is_syntax_error = False
    syntax_error_details = "None"

    # Check for collection / syntax errors
    if (
        "ERRORS" in output_text
        or "SyntaxError" in output_text
        or "Interrupted: 1 error during collection" in output_text
    ):
        is_syntax_error = True
        syntax_error_details = output_text
        logger.error(
            "[%s] Fatal Pytest Collection / Syntax Error detected:\n%s",
            "Pytest",
            output_text,
        )

    for line in reversed(output_text.splitlines()):
        stripped = line.strip()
        if any(
            kw in stripped
            for kw in ["passed", "failed", "error", "skipped", "no tests ran"]
        ):
            summary = stripped
            break

    summary_lower = summary.lower()
    tests_passed = (
        not is_syntax_error
        and "failed" not in summary_lower
        and "error" not in summary_lower
    )

    missing_lines = "None"
    is_100_percent = False
    in_coverage_section = False

    # Normalize source file path representation for matching in pytest coverage output
    target_source_normalized = (
        Path(source_file_path).as_posix().lower() if source_file_path else None
    )

    for line in output_text.splitlines():
        if "tests coverage" in line:
            in_coverage_section = True
            continue
        if in_coverage_section and ".py" in line and "TOTAL" not in line:
            # If a specific source file path is provided, ensure this coverage row matches it
            if target_source_normalized:
                line_normalized = line.replace("\\", "/").lower()
                if target_source_normalized not in line_normalized:
                    continue

            parts = line.split()
            if len(parts) >= MIN_PARTS_FOR_COVERAGE and parts[2].isdigit():
                miss_count = int(parts[2])
                cover_str = parts[3] if len(parts) > MIN_PARTS_FOR_COVERAGE else ""
                if miss_count == 0 or cover_str == "100%":
                    is_100_percent = True
                    missing_lines = "None (100% coverage)"
                else:
                    is_100_percent = False
                    missing_lines = (
                        " ".join(parts[MIN_PARTS_WITH_MISSING:])
                        if len(parts) > MIN_PARTS_WITH_MISSING
                        else f"Missing lines (Miss count: {miss_count})"
                    )
                break

    return (
        summary,
        missing_lines,
        tests_passed,
        is_100_percent,
        is_syntax_error,
        syntax_error_details,
    )


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


def is_syntactically_valid(code_content: str) -> bool:
    """Check if the code string is valid Python syntax."""
    try:
        ast.parse(code_content)

    except SyntaxError:
        return False
    return True


def parse_basedpyright_summary(output_text: str) -> str:
    """Extract the final summary line from basedpyright output."""
    for line in reversed(output_text.splitlines()):
        stripped = line.strip()
        if "error" in stripped or "warning" in stripped or "note" in stripped:
            return stripped
    return "No summary found"


def parse_ruff_summary(output_text: str) -> str:
    """Extract summary line from ruff output."""
    for line in output_text.splitlines():
        stripped = line.strip()
        if (
            "Ruff Status:" in stripped
            or "All checks passed!" in stripped
            or "Found " in stripped
        ):
            return stripped
    lines = [
        line.strip()
        for line in output_text.splitlines()
        if line.strip() and "|" not in line
    ]
    return lines[-1] if lines else "No summary found"


def filter_ruff_output(output_text: str) -> str:
    """Remove config incompatibility warning lines from ruff output."""
    filtered_lines = [
        line
        for line in output_text.splitlines()
        if not line.strip().lower().startswith("warning:")
    ]
    return "\n".join(filtered_lines)


def extract_uncovered_blocks(coverage_text: str) -> list[str]:
    """Extract the first line of each contiguous block of uncovered lines (!)."""
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
        if cover_line.startswith("!"):
            if idx >= len(source_lines):
                continue

            actual_code = source_lines[idx].strip()

            guard_condition = "Unknown condition"
            for prev_idx in range(idx - 1, max(-1, idx - MAX_BACKWARD_LOOKUP), -1):
                if prev_idx < len(source_lines):
                    prev_line = source_lines[prev_idx].strip()
                    if prev_line.startswith("if "):
                        guard_condition = prev_line
                        break

            hints.append(
                f"GENERIC HINT (Line {idx + 1}): The statement `{actual_code}` "
                f"inside the block guarded by `{guard_condition}` was never executed. "
                "This means your tests never successfully entered this branch. "
                "Analyze what variables or state values are required for "
                f"`{guard_condition}` to evaluate to True and allow execution to "
                f"reach `{actual_code}`.",
            )

    return hints


def read_local_files(
    test_file_path: str,
    source_file_path: str,
    prefix: str,
) -> tuple[str, str, str]:
    """Read local dynamic test, coverage, and log files safely using Path."""
    logger.info(
        "[%s] Reading local dynamic test, coverage, and log files for payload...",
        prefix,
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


def is_valid_gemini_code(code: str) -> bool:
    """Validate that Gemini returned actual code (>5 lines and comment tag)."""
    lines = [line for line in code.splitlines() if line.strip()]
    if len(lines) <= MIN_LINES_FOR_GEMINI_CODE:
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
        logger.info("[%s] Code Diff:\n%s", prefix, "".join(diff))

    test_path.write_text(new_code, encoding="utf-8")
    logger.info("[%s] Saved updated test script to %s", prefix, test_path)
