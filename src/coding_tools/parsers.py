# src/coding_tools/parsers.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse local files, run test/lint commands, diff, and check code."""

from __future__ import annotations

import ast
import difflib
import subprocess
from pathlib import Path

from coding_tools.file_handler import (
    get_basedpyright_log_path,
    get_coverage_annotation_path,
    get_pytest_log_path,
    get_ruff_log_path,
)
from coding_tools.logger import get_project_logger
from coding_tools.workspace_guard import WorkspaceGuard
from coding_tools.workspace_stamper import TargetWorkspace, WorkspaceStamper

logger = get_project_logger(__name__)

MIN_PARTS_FOR_COVERAGE = 3
MIN_PARTS_WITH_MISSING = 4
MAX_BACKWARD_LOOKUP = 5
MIN_LINES_FOR_LLM_CODE = 5


def run_pytest_command(
    test_file_path: str,
    source_file_path: str,
    prefix: str,
) -> None:
    """Run pytest with branch coverage and save output to pytest log.

    Uses uv, pytest, cov-branch, term-missing, and annotate.
    """
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
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=annotate:.coverage_annotations",
        test_file_path,
    ]
    cmd_str = " ".join(cmd_list)
    logger.progress(prefix, f"Run `{cmd_str}`")

    result = subprocess.run(  # noqa: S603
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    output_path = get_pytest_log_path(test_file_path)
    full_content = f"$ {cmd_str}\n\n{result.stdout}\n{result.stderr}"
    output_path.write_text(full_content, encoding="utf-8")


def run_basedpyright_command(test_file_path: str, prefix: str) -> str:
    """Run basedpyright on test file and save output to log.

    Uses uv and basedpyright.
    """
    cmd_list = [
        "uv",
        "run",
        "basedpyright",
        test_file_path,
    ]
    cmd_str = " ".join(cmd_list)
    logger.progress(prefix, f"Run `{cmd_str}`")

    result = subprocess.run(  # noqa: S603
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    output_path = get_basedpyright_log_path(test_file_path)
    full_content = f"$ {cmd_str}\n\n{result.stdout}\n{result.stderr}"
    output_path.write_text(full_content, encoding="utf-8")
    return full_content


def run_ruff_command(test_file_path: str, prefix: str) -> str:
    """Run ruff check with fix option and save output to log.

    Uses uv and ruff check.
    """
    cmd_list = [
        "uv",
        "run",
        "ruff",
        "check",
        test_file_path,
        "--fix",
    ]
    cmd_str = " ".join(cmd_list)
    logger.progress(prefix, f"Run `{cmd_str}`")

    result = subprocess.run(  # noqa: S603
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )

    summary_line = "Passed all checks"
    for line in result.stdout.splitlines():
        if "Found " in line or "Passed all checks" in line:
            summary_line = line.strip()
            break
    if result.returncode != 0 and "Found " not in result.stdout:
        summary_line = f"Ruff failed with exit code {result.returncode}"

    logger.progress(prefix, f"Ruff: {summary_line}")

    output_path = get_ruff_log_path(test_file_path)
    full_content = (
        f"$ {cmd_str}\n\nRuff Summary: {summary_line}\n\n"
        f"{result.stdout}\n{result.stderr}"
    )
    output_path.write_text(full_content, encoding="utf-8")
    return full_content


def _check_pytest_syntax_error(output_text: str) -> tuple[bool, str]:
    """Check pytest output for collection or syntax errors.

    True if ERRORS, SyntaxError, or collection stop found.
    """
    if (
        "ERRORS" in output_text
        or "SyntaxError" in output_text
        or "Interrupted: 1 error during collection" in output_text
    ):
        logger.error(
            None,
            f"Fatal Pytest Collection / Syntax Error detected:\n{output_text}",
        )
        return True, output_text
    return False, "None"


def _extract_pytest_summary(output_text: str) -> str:
    """Extract summary line from pytest output text by scanning reversed lines."""
    summary = "No summary found"
    for line in reversed(output_text.splitlines()):
        stripped = line.strip()
        if any(
            kw in stripped
            for kw in ["passed", "failed", "error", "skipped", "no tests ran"]
        ):
            summary = stripped
            break
    return summary


def _extract_coverage_metrics(
    output_text: str,
    target_source_normalized: str | None,
) -> tuple[str, bool]:
    """Extract missing lines and 100 percent coverage flag from pytest output.

    Scans coverage section for target source path or basename.
    """
    missing_lines = "None"
    is_100_percent = False
    in_coverage_section = False

    for line in output_text.splitlines():
        if "coverage" in line.lower() and ("---" in line or "===" in line):
            in_coverage_section = True
            continue
        if in_coverage_section and ".py" in line and "TOTAL" not in line:
            if target_source_normalized:
                line_normalized = line.replace("\\", "/").lower()
                source_basename = Path(target_source_normalized).name.lower()
                if (
                    target_source_normalized not in line_normalized
                    and source_basename not in line_normalized
                ):
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
    return missing_lines, is_100_percent


def parse_pytest_results(
    output_text: str,
    source_file_path: str | None = None,
) -> tuple[str, str, bool, bool, bool, str]:
    """Parse pytest output for test results, coverage, and errors.

    Calls syntax check, summary extraction, and coverage metrics.
    """
    is_syntax_error, syntax_error_details = _check_pytest_syntax_error(
        output_text,
    )
    summary = _extract_pytest_summary(output_text)

    summary_lower = summary.lower()
    tests_passed = (
        not is_syntax_error
        and "failed" not in summary_lower
        and "error" not in summary_lower
    )

    target_source_normalized = (
        Path(source_file_path).as_posix().lower() if source_file_path else None
    )
    missing_lines, is_100_percent = _extract_coverage_metrics(
        output_text,
        target_source_normalized,
    )

    return (
        summary,
        missing_lines,
        tests_passed,
        is_100_percent,
        is_syntax_error,
        syntax_error_details,
    )


def extract_pytest_warnings(pytest_output: str) -> str:
    """Extract warnings summary from pytest output text.

    Stops at docs or coverage lines.
    """
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


def extract_pytest_errors(pytest_output: str) -> str:
    """Get lines starting with E from pytest output and log warnings."""
    lines = pytest_output.splitlines()
    error_lines = [line for line in lines if line.startswith("E ")]
    cleaned = "\n".join(error_lines).strip()
    if cleaned:
        logger.warning(
            None,
            f"Pytest Assertion/Execution Errors detected (E lines):\n{cleaned}",
        )
    return cleaned or "None"


def is_syntactically_valid(code_content: str) -> bool:
    """Check if code string has valid Python syntax via ast parse.

    False if SyntaxError raised.
    """
    try:
        ast.parse(code_content)
    except SyntaxError:
        return False
    return True


def parse_basedpyright_summary(output_text: str) -> str:
    """Extract final summary line from basedpyright output.

    Scans reversed lines for error, warning, or note.
    """
    for line in reversed(output_text.splitlines()):
        stripped = line.strip()
        if "error" in stripped or "warning" in stripped or "note" in stripped:
            return stripped
    return "No summary found"


def parse_ruff_summary(output_text: str) -> str:
    """Extract summary line from ruff output.

    Scans for status, checks passed, or found messages.
    """
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
    """Clear config conflict warning lines starting with warning: from ruff output."""
    filtered_lines = [
        line
        for line in output_text.splitlines()
        if not line.strip().lower().startswith("warning:")
    ]
    return "\n".join(filtered_lines)


def extract_uncovered_blocks(coverage_text: str) -> list[str]:
    """Get 1st line of each contiguous block of uncovered lines starting with !."""
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
    """Scan uncovered lines and build hints.

    Reads coverage annotation and source files.
    """
    cover_path = get_coverage_annotation_path(source_file_path)
    if not cover_path.exists():
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
            for prev_idx in range(
                idx - 1,
                max(-1, idx - MAX_BACKWARD_LOOKUP),
                -1,
            ):
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
    """Read test content, coverage report, and pytest log.

    Handles missing coverage annotation file.
    """
    logger.progress(
        prefix,
        "Read local dynamic test, coverage, and log files",
    )
    test_content = Path(test_file_path).read_text(encoding="utf-8")

    cover_path = get_coverage_annotation_path(source_file_path)
    if not cover_path.exists():
        cover_path = Path(f"{source_file_path},cover")

    if cover_path.exists():
        coverage_content = cover_path.read_text(encoding="utf-8")
    else:
        coverage_content = (
            "No coverage report built due to pytest collection or execution error."
        )

    pytest_output = get_pytest_log_path(test_file_path).read_text(encoding="utf-8")

    return test_content, coverage_content, pytest_output


def run_preflight_compliance_and_validation(
    test_file_path: str,
    prefix: str,
) -> tuple[bool, list[str]]:
    """Run stamper and prioritized static validation checks.

    Checks file existence, length, syntax, static isolation, and SPDX header.
    """
    logger.progress(prefix, "Run pre-pytest checks")
    prioritized_errors: list[str] = []
    test_path = Path(test_file_path)

    try:
        project_dir = Path.cwd()
        workspace = TargetWorkspace(
            project_dir=project_dir,
            target_path=test_path.resolve(),
            run_path_stamp=True,
            run_license_stamp=True,
            extracted_license_id="Apache-2.0",
        )
        stamper = WorkspaceStamper(workspace=workspace)
        stamper.run()
        logger.progress(
            prefix,
            "Done workspace_stamper",
        )
    except Exception:
        logger.exception(
            prefix,
            "Failed workspace_stamper",
        )

    if not test_path.exists():
        return False, ["Test file does not exist."]

    code_content = test_path.read_text(encoding="utf-8")

    # Priority 1: Code Length Check (> 5 lines)
    lines = [line for line in code_content.splitlines() if line.strip()]
    len_ok = len(lines) > MIN_LINES_FOR_LLM_CODE
    if not len_ok:
        prioritized_errors.append(
            f"(Priority 1) Code line count ({len(lines)}) is "
            f"<= {MIN_LINES_FOR_LLM_CODE}.",
        )

    # Priority 2: Syntax Validity Check (ast.parse)
    syntax_ok = is_syntactically_valid(code_content)
    if not syntax_ok:
        prioritized_errors.append(
            "(Priority 2) Code failed Python syntax validation "
            "(SyntaxError/ast.parse).",
        )

    # Priority 3: Static tmp_path Isolation Check (WorkspaceGuard)
    guard = WorkspaceGuard(project_path=Path.cwd())
    is_isolated, static_errors = guard.check_static_isolation(test_path, prefix)
    if not is_isolated:
        prioritized_errors.extend(
            [
                f"(Priority 3) Static Isolation Violation: {err}"
                for err in static_errors
            ],
        )

    # Priority 4: SPDX Header Check
    has_spdx = any(
        "SPDX-License-Identifier" in line for line in code_content.splitlines()
    )
    if not has_spdx:
        prioritized_errors.append(
            "(Priority 4) Code is missing required SPDX license header tags.",
        )

    all_passed = len(prioritized_errors) == 0
    status_label = "PASSED" if all_passed else "FAILED"
    synthesis_msg = (
        f"Pre-Pytest Run Synthesis Status: [{status_label}] | "
        f"1. Length: {'PASS' if len_ok else 'FAIL'} | "
        f"2. Syntax: {'PASS' if syntax_ok else 'FAIL'} | "
        f"3. Isolation: {'PASS' if is_isolated else 'FAIL'} | "
        f"4. SPDX: {'PASS' if has_spdx else 'FAIL'}"
    )

    if all_passed:
        logger.progress(prefix, synthesis_msg)
    else:
        logger.warning(prefix, synthesis_msg)

    return all_passed, prioritized_errors


def validate_llm_code(code: str) -> tuple[bool, str]:
    """Check LLM code length, comment tags, syntax, and isolation.

    Writes temp file and clears after check.
    """
    lines = [line for line in code.splitlines() if line.strip()]
    if len(lines) <= MIN_LINES_FOR_LLM_CODE:
        return (
            False,
            (
                f"(Priority 1) Code line count ({len(lines)}) is "
                f"<= {MIN_LINES_FOR_LLM_CODE}"
            ),
        )
    if not any(line.strip().startswith("#") for line in lines):
        return (
            False,
            "(Priority 4) Code is missing required comment tags (e.g., # SPDX header)",
        )
    if not is_syntactically_valid(code):
        return False, "(Priority 2) Code failed Python syntax validation (SyntaxError)"

    guard = WorkspaceGuard(project_path=Path.cwd())
    temp_path = Path("temp_llm_check.py")
    temp_path.write_text(code, encoding="utf-8")
    is_isolated, iso_errors = guard.check_static_isolation(temp_path, "Guard")
    if temp_path.exists():
        temp_path.unlink()

    if not is_isolated:
        return False, f"(Priority 3) Static Isolation Violation: {iso_errors[0]}"

    return True, "Valid"


def process_and_save_code(new_code: str, test_file_path: str, prefix: str) -> None:
    """Yield diff statistics, log diff, and write new test code.

    Uses unified diff and overwrites test file.
    """
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
        logger.progress(prefix, f"Code Diff:\n{''.join(diff)}")

    test_path.write_text(new_code, encoding="utf-8")
    logger.progress(prefix, f"Done. Saved script to {test_path}")
