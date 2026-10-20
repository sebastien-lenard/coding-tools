# tests/unit/test_parsers.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for parsers module."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from coding_tools import parsers

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class PytestResultTestCase:
    """Test case data structure for pytest result parsing tests."""

    output: str
    expected_summary: str
    expected_missing: str
    expected_passed: bool
    expected_100: bool
    expected_syntax: bool


def test_run_pytest_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test running pytest command."""
    monkeypatch.chdir(tmp_path)
    captured_cmds: list[list[str]] = []

    def mock_run(
        cmd_list: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured_cmds.append(cmd_list)
        return subprocess.CompletedProcess(
            cmd_list,
            0,
            stdout="=== 1 passed in 0.01s ===",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    parsers.run_pytest_command(
        "tests/unit/test_dummy.py",
        "src/coding_tools/parsers.py",
        "PREFIX",
    )
    assert len(captured_cmds) == 1
    log_file = tmp_path / "unit-test-test_dummy.txt"
    assert log_file.exists()
    assert "1 passed" in log_file.read_text(encoding="utf-8")

    parsers.run_pytest_command(
        "tests/unit/test_dummy.py",
        "other_dir/parsers.py",
        "PREFIX",
    )
    assert log_file.exists()


def test_run_basedpyright_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test running basedpyright command."""
    monkeypatch.chdir(tmp_path)

    def mock_run(
        cmd_list: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd_list,
            0,
            stdout="0 errors",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = parsers.run_basedpyright_command(
        "tests/unit/test_dummy.py",
        "PREFIX",
    )
    assert "0 errors" in res
    assert (tmp_path / "based-pyright-test_dummy.txt").exists()


def test_run_ruff_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test running ruff command."""
    monkeypatch.chdir(tmp_path)

    def mock_run(
        cmd_list: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd_list,
            0,
            stdout="All checks passed!",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = parsers.run_ruff_command(
        "tests/unit/test_dummy.py",
        "PREFIX",
    )
    assert "All checks passed!" in res
    assert (tmp_path / "ruff-test_dummy.txt").exists()


def test_run_ruff_command_non_zero_exit_without_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test running ruff command with non-zero exit without found."""
    monkeypatch.chdir(tmp_path)

    def mock_run(
        cmd_list: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd_list,
            1,
            stdout="Some generic error",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = parsers.run_ruff_command(
        "tests/unit/test_dummy.py",
        "PREFIX",
    )
    assert "Ruff failed with exit code 1" in res
    assert (tmp_path / "ruff-test_dummy.txt").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        PytestResultTestCase(
            output="=== 1 passed in 0.01s ===",
            expected_summary="=== 1 passed in 0.01s ===",
            expected_missing="None",
            expected_passed=True,
            expected_100=False,
            expected_syntax=False,
        ),
        PytestResultTestCase(
            output="tests/unit/test_foo.py failed - AssertionError",
            expected_summary="tests/unit/test_foo.py failed - AssertionError",
            expected_missing="None",
            expected_passed=False,
            expected_100=False,
            expected_syntax=False,
        ),
        PytestResultTestCase(
            output="ERRORS during collection\n=== 1 error in 0.05s ===",
            expected_summary="=== 1 error in 0.05s ===",
            expected_missing="None",
            expected_passed=False,
            expected_100=False,
            expected_syntax=True,
        ),
        PytestResultTestCase(
            output=(
                "tests coverage\ncoding_tools/foo.py   10   0   100%\n"
                "TOTAL   10   0   100%\n=== 1 passed ==="
            ),
            expected_summary="=== 1 passed ===",
            expected_missing="None (100% coverage)",
            expected_passed=True,
            expected_100=True,
            expected_syntax=False,
        ),
        PytestResultTestCase(
            output=(
                "tests coverage\ncoding_tools/foo.py   10   2   80%   5 6\n"
                "TOTAL   10   2   80%\n=== 1 passed ==="
            ),
            expected_summary="=== 1 passed ===",
            expected_missing="5 6",
            expected_passed=True,
            expected_100=False,
            expected_syntax=False,
        ),
        PytestResultTestCase(
            output=(
                "tests coverage\ncoding_tools/foo.py   10   2   80%\n"
                "TOTAL   10   2   80%\n=== 1 passed ==="
            ),
            expected_summary="=== 1 passed ===",
            expected_missing="Missing lines (Miss count: 2)",
            expected_passed=True,
            expected_100=False,
            expected_syntax=False,
        ),
    ],
)
def test_parse_pytest_results(
    test_case: PytestResultTestCase,
) -> None:
    """Test parsing pytest results."""
    summary, missing, passed, is_100, is_syntax, _details = (
        parsers.parse_pytest_results(test_case.output)
    )
    assert summary == test_case.expected_summary
    assert missing == test_case.expected_missing
    assert passed == test_case.expected_passed
    assert is_100 == test_case.expected_100
    assert is_syntax == test_case.expected_syntax


def test_parse_pytest_results_with_source_filter() -> None:
    """Test parsing pytest results with source file filtering."""
    output = (
        "tests coverage\n"
        "src/coding_tools/bar.py   10   0   100%\n"
        "src/coding_tools/foo.py   10   0   100%\n"
        "TOTAL   20   0   100%\n"
        "=== 1 passed ==="
    )
    _, missing, _, is_100, _, _ = parsers.parse_pytest_results(
        output,
        source_file_path="src/coding_tools/foo.py",
    )
    assert is_100 is True
    assert missing == "None (100% coverage)"


def test_is_syntactically_valid() -> None:
    """Test is_syntactically_valid for valid and invalid syntax."""
    assert parsers.is_syntactically_valid("x = 1") is True
    assert parsers.is_syntactically_valid("x = (") is False


def test_extract_pytest_warnings() -> None:
    """Test extracting pytest warnings."""
    output_with_warnings = (
        "\\\nSome output\n-- Warnings summary --\n"
        "Line 1 warning\nLine 2 warning\n"
        "-- Docs: https://docs.pytest.org\nSome more output\n"
    )
    res = parsers.extract_pytest_warnings(output_with_warnings)
    assert "Line 1 warning" in res
    assert "Line 2 warning" in res

    output_without_warnings = "No warnings here"
    assert parsers.extract_pytest_warnings(output_without_warnings) == "None"


def test_extract_pytest_errors() -> None:
    """Test extracting pytest errors."""
    output_with_errors = "E   AssertionError: assert 1 == 2\nsome traceback"
    res = parsers.extract_pytest_errors(output_with_errors)
    assert "AssertionError" in res

    assert parsers.extract_pytest_errors("no errors here") == "None"


def test_parse_basedpyright_summary() -> None:
    """Test parsing basedpyright summary."""
    text = "\n    analyzing file...\n    0 errors, 1 warning, 0 notes\n    "
    assert parsers.parse_basedpyright_summary(text) == "0 errors, 1 warning, 0 notes"
    assert parsers.parse_basedpyright_summary("no info") == "No summary found"


def test_parse_ruff_summary() -> None:
    """Test parsing ruff summary."""
    assert parsers.parse_ruff_summary("All checks passed!") == "All checks passed!"
    assert parsers.parse_ruff_summary("Found 2 error(s).") == "Found 2 error(s)."
    assert parsers.parse_ruff_summary("some random output\nother line") == (
        "other line"
    )
    assert parsers.parse_ruff_summary("") == "No summary found"


def test_filter_ruff_output() -> None:
    """Test filtering ruff output."""
    text = "\\\nWarning: Incompatible config\nAll checks passed!\n"
    filtered = parsers.filter_ruff_output(text)
    assert "Warning:" not in filtered
    assert "All checks passed!" in filtered


def test_extract_uncovered_blocks() -> None:
    """Test extracting uncovered blocks."""
    cov_text = (
        "\n    line 1\n    ! line 2 uncovered\n    ! line 3 uncovered\n"
        "    line 4\n    ! line 5 alone\n    "
    )
    blocks = parsers.extract_uncovered_blocks(cov_text)
    assert len(blocks) == 2
    assert blocks[0].strip() == "! line 2 uncovered"
    assert blocks[1].strip() == "! line 5 alone"

    cov_text_trailing = "\n    line 1\n    ! line 2 trailing\n    ! line 3 trailing"
    blocks_trailing = parsers.extract_uncovered_blocks(cov_text_trailing)
    assert len(blocks_trailing) == 1
    assert blocks_trailing[0].strip() == "! line 2 trailing"


def test_generate_coverage_hints(tmp_path: Path) -> None:
    """Test generating coverage hints."""
    assert parsers.generate_coverage_hints(str(tmp_path / "nonexistent.py")) == []

    source_file = tmp_path / "dummy.py"
    cover_file = tmp_path / "dummy.py,cover"
    cover_file.write_text("! line 1", encoding="utf-8")
    assert parsers.generate_coverage_hints(str(source_file)) == []

    source_file.write_text(
        "x = 1 and 2\nif True:\n    pass\nexcept Exception:\n    pass\n",
        encoding="utf-8",
    )
    cover_file.write_text(
        "! line 1\n! line 2\n! line 3\n! line 4\n! line 5 out of bounds\n",
        encoding="utf-8",
    )
    hints = parsers.generate_coverage_hints(str(source_file))
    assert any("and" in h for h in hints)
    assert any("if" in h for h in hints)
    assert any("except" in h for h in hints)


def test_generate_coverage_hints_index_out_of_bounds(tmp_path: Path) -> None:
    """Test coverage hints index out of bounds."""
    source_file = tmp_path / "dummy.py"
    source_file.write_text("x = 1", encoding="utf-8")
    cover_file = tmp_path / "dummy.py,cover"
    cover_file.write_text("line 0\n! line 1 out of bounds", encoding="utf-8")
    hints = parsers.generate_coverage_hints(str(source_file))
    assert hints == []


def test_read_local_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test reading local files."""
    monkeypatch.chdir(tmp_path)
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("def test_foo(): pass", encoding="utf-8")

    log_file = tmp_path / "unit-test-test_dummy.txt"
    log_file.write_text("pytest log content", encoding="utf-8")

    cover_file = tmp_path / "src_parsers.py,cover"
    cover_file.write_text("coverage content", encoding="utf-8")

    test_content, coverage_content, pytest_output = parsers.read_local_files(
        str(test_file),
        str(tmp_path / "src_parsers.py"),
        "PREFIX",
    )
    assert test_content == "def test_foo(): pass"
    assert coverage_content == "coverage content"
    assert pytest_output == "pytest log content"

    cover_file.unlink()
    _, coverage_content_missing, _ = parsers.read_local_files(
        str(test_file),
        str(tmp_path / "src_parsers.py"),
        "PREFIX",
    )
    assert "No coverage report generated" in coverage_content_missing


@pytest.mark.parametrize(
    ("code", "expected_valid", "expected_reason"),
    [
        ("# comment\nline2\nline3\nline4\nline5\nline6", True, "Valid"),
        ("print('hello')\n" * 3, False, "Code line count"),
        (
            "x = 1\nx = 2\nx = 3\nx = 4\nx = 5\nx = 6",
            False,
            "missing required comment tags",
        ),
        ("# comment\nx = (\nline3\nline4\nline5\nline6", False, "SyntaxError"),
    ],
)
def test_validate_llm_code(
    code: str,
    expected_valid: bool,
    expected_reason: str,
) -> None:
    """Test validating LLM code."""
    is_valid, reason = parsers.validate_llm_code(code)
    assert is_valid == expected_valid
    assert expected_reason in reason


def test_process_and_save_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test processing and saving code."""
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("old code", encoding="utf-8")

    captured_diffs: list[str] = []

    def mock_info(msg: str, *args: object, **kwargs: object) -> None:
        formatted = msg % args if args else msg
        if "Code Diff:" in formatted:
            captured_diffs.append(formatted)

    monkeypatch.setattr(parsers.logger, "info", mock_info)

    parsers.process_and_save_code("new code", str(test_file), "PREFIX")
    assert test_file.read_text(encoding="utf-8") == "new code"
    assert len(captured_diffs) == 1


def test_process_and_save_code_no_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test processing and saving code with no diff."""
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("same code", encoding="utf-8")

    captured_diffs: list[str] = []

    def mock_info(msg: str, *args: object, **kwargs: object) -> None:
        formatted = msg % args if args else msg
        if "Code Diff:" in formatted:
            captured_diffs.append(formatted)

    monkeypatch.setattr(parsers.logger, "info", mock_info)

    parsers.process_and_save_code("same code", str(test_file), "PREFIX")
    assert test_file.read_text(encoding="utf-8") == "same code"
    assert len(captured_diffs) == 0
