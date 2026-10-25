# tests/unit/test_parsers.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for parsers."""

from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

from coding_tools import parsers
from coding_tools.logger import get_project_logger

logger = get_project_logger(__name__)


def test_run_pytest_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class MockCompletedProcess:
        returncode = 0
        stdout = "passed"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockCompletedProcess())
    source_file = tmp_path / "src" / "coding_tools" / "dummy.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("x = 1\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_dummy(): assert True\n", encoding="utf-8")

    parsers.run_pytest_command(str(test_file), str(source_file), "prefix")
    assert parsers.get_pytest_log_path(str(test_file)).exists()


def test_run_pytest_command_absolute_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class MockCompletedProcess:
        returncode = 0
        stdout = "passed"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockCompletedProcess())
    source_file = tmp_path / "outside" / "dummy.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("x = 1\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_dummy(): assert True\n", encoding="utf-8")

    parsers.run_pytest_command(str(test_file), str(source_file), "prefix")
    assert parsers.get_pytest_log_path(str(test_file)).exists()


def test_run_basedpyright_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class MockCompletedProcess:
        returncode = 0
        stdout = "0 errors"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockCompletedProcess())
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_dummy(): assert True\n", encoding="utf-8")

    res = parsers.run_basedpyright_command(str(test_file), "prefix")
    assert "0 errors" in res


def test_run_ruff_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class MockCompletedProcess:
        returncode = 0
        stdout = "Found 1 error.\nAll checks passed!"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockCompletedProcess())
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_dummy(): assert True\n", encoding="utf-8")

    res = parsers.run_ruff_command(str(test_file), "prefix")
    assert "Ruff Summary" in res


def test_run_ruff_command_failure_without_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class MockCompletedProcess:
        returncode = 1
        stdout = "Some error"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockCompletedProcess())
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_dummy(): assert True\n", encoding="utf-8")

    res = parsers.run_ruff_command(str(test_file), "prefix")
    assert "Ruff failed with exit code 1" in res


@pytest.mark.parametrize(
    "output,expected_err,expected_syntax",
    [
        ("ERRORS", True, True),
        ("SyntaxError", True, True),
        ("Interrupted: 1 error during collection", True, True),
        ("== 1 passed in 0.01s ==", False, False),
    ],
)
def test_parse_pytest_results(output: str, expected_err: bool, expected_syntax: bool) -> None:
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output)
    assert is_syntax == expected_syntax


def test_parse_pytest_results_with_source(tmp_path: Path) -> None:
    source = tmp_path / "src" / "coding_tools" / "parsers.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# parser", encoding="utf-8")
    
    output = "=== 1 passed in 0.1s ===\n---------- coverage: platform win32 ----------\nsrc/coding_tools/parsers.py 10 0 100%"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output, str(source))
    assert is_100

    output_missing = "=== 1 failed in 0.1s ===\n---------- coverage: platform win32 ----------\nsrc/coding_tools/parsers.py 10 2 50% 10 15"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_missing, str(source))
    assert not is_100

    output_missing_no_parts = "=== 1 failed in 0.1s ===\n---------- coverage: platform win32 ----------\nsrc/coding_tools/parsers.py 10 2 50%"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_missing_no_parts, str(source))
    assert not is_100

    output_other_file = "=== 1 passed in 0.1s ===\n---------- coverage: platform win32 ----------\nother_file.py 10 0 100%\nsrc/coding_tools/parsers.py 10 0 100%"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_other_file, str(source))
    assert is_100

    output_non_matching = "=== 1 passed in 0.1s ===\n---------- coverage: platform win32 ----------\nother_file.py 10 0 100%"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_non_matching, str(source))
    assert not is_100

    output_cov_branches = "=== 1 passed in 0.1s ===\n---------- coverage: platform win32 ----------\n=== heading ===\nother_file.py 10 0 100%\nsrc/coding_tools/parsers.py 10 2 50%"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_cov_branches, str(source))
    assert not is_100

    output_basename_match = "=== 1 passed in 0.1s ===\n---------- coverage: platform win32 ----------\nparsers.py 10 0 100%"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_basename_match, str(source))
    assert is_100

    output_loop_continue = "=== 1 passed in 0.1s ===\n---------- coverage: platform win32 ----------\nheader line\nother_file.py 10 0 100%\nsrc/coding_tools/parsers.py 10 0 100%"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_loop_continue, str(source))
    assert is_100

    output_branch_coverage_parts = "=== 1 passed in 0.1s ===\n---------- coverage: platform win32 ----------\nsrc/coding_tools/parsers.py 10 0 100% 1 2"
    summary, missing, passed, is_100, is_syntax, details = parsers.parse_pytest_results(output_branch_coverage_parts, str(source))
    assert is_100


def test_extract_pytest_warnings() -> None:
    text = "warnings summary\nwarning line 1\n-- Docs: https://..."
    assert "warning line 1" in parsers.extract_pytest_warnings(text)
    assert parsers.extract_pytest_warnings("no warnings") == "None"


def test_extract_pytest_errors() -> None:
    text = "E assert False"
    assert "assert False" in parsers.extract_pytest_errors(text)
    assert parsers.extract_pytest_errors("no errors") == "None"


def test_parse_basedpyright_summary() -> None:
    text = "some output\n1 error, 2 warnings"
    assert "1 error" in parsers.parse_basedpyright_summary(text)
    assert parsers.parse_basedpyright_summary("no summary") == "No summary found"


def test_parse_ruff_summary() -> None:
    text = "Ruff Status: ok"
    assert parsers.parse_ruff_summary(text) == "Ruff Status: ok"
    text2 = "line1\nline2"
    assert parsers.parse_ruff_summary(text2) == "line2"
    assert parsers.parse_ruff_summary("   \n") == "No summary found"
    text3 = "All checks passed!"
    assert "All checks passed!" in parsers.parse_ruff_summary(text3)
    text4 = "Found 1 error"
    assert parsers.parse_ruff_summary(text4) == "Found 1 error"


def test_filter_ruff_output() -> None:
    text = "warning: some config warning\nnormal line"
    assert "warning:" not in parsers.filter_ruff_output(text)


def test_extract_uncovered_blocks() -> None:
    text = " ! line1\n   line2\n ! line3\n ! line4"
    blocks = parsers.extract_uncovered_blocks(text)
    assert len(blocks) == 2

    text_trailing = " ! line1\n   line2\n ! line3"
    blocks_trailing = parsers.extract_uncovered_blocks(text_trailing)
    assert len(blocks_trailing) == 2


def test_generate_coverage_hints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.py"
    source.write_text("if True:\n    x = 1\n", encoding="utf-8")
    cover = tmp_path / "source.py,cover"
    cover.write_text("\n!     x = 1\n", encoding="utf-8")
    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: cover)
    hints = parsers.generate_coverage_hints(str(source))
    assert len(hints) == 1

    source2 = tmp_path / "source2.py"
    source2.write_text("x = 0\nif True:\n    x = 1\n", encoding="utf-8")
    cover2 = tmp_path / "source2.py,cover"
    cover2.write_text("\n\n!     x = 1\n", encoding="utf-8")
    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: cover2)
    hints2 = parsers.generate_coverage_hints(str(source2))
    assert len(hints2) == 1

    source3 = tmp_path / "source3.py"
    source3.write_text("x = 1\n", encoding="utf-8")
    cover3 = tmp_path / "source3.py,cover"
    cover3.write_text("! x = 1\n", encoding="utf-8")
    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: cover3)
    hints3 = parsers.generate_coverage_hints(str(source3))
    assert len(hints3) == 1

    source4 = tmp_path / "source4.py"
    source4.write_text("x = 1\n", encoding="utf-8")
    cover4 = tmp_path / "source4.py,cover"
    cover4.write_text("x = 1\n! extra\n", encoding="utf-8")
    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: cover4)
    hints4 = parsers.generate_coverage_hints(str(source4))
    assert len(hints4) == 0


def test_generate_coverage_hints_fallback_cover(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.py"
    source.write_text("x = 1\n", encoding="utf-8")
    cover = tmp_path / "source.py,cover"
    cover.write_text("! x = 1\n", encoding="utf-8")
    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: tmp_path / "nonexistent")
    hints = parsers.generate_coverage_hints(str(source))
    assert len(hints) == 1


def test_generate_coverage_hints_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert parsers.generate_coverage_hints(str(tmp_path / "nonexistent.py")) == []

    source = tmp_path / "source.py"
    source.write_text("x = 1\n", encoding="utf-8")
    cover = tmp_path / "source.py,cover"
    cover.write_text("! x = 1\n", encoding="utf-8")
    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: cover)
    assert parsers.generate_coverage_hints(str(tmp_path / "nonexistent_source.py")) == []


def test_read_local_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_file = tmp_path / "test.py"
    test_file.write_text("test", encoding="utf-8")
    source_file = tmp_path / "source.py"
    source_file.write_text("source", encoding="utf-8")
    log_file = tmp_path / ".pytest_logs" / "test.py.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("log", encoding="utf-8")
    
    cover_file = tmp_path / "source.py.cover"
    cover_file.write_text("cover", encoding="utf-8")
    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: cover_file)
    
    import unittest.mock
    with unittest.mock.patch("coding_tools.parsers.get_pytest_log_path", return_value=log_file):
        t, c, p = parsers.read_local_files(str(test_file), str(source_file), "prefix")
        assert t == "test"


def test_read_local_files_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_file = tmp_path / "test.py"
    test_file.write_text("test", encoding="utf-8")
    source_file = tmp_path / "source.py"
    source_file.write_text("source", encoding="utf-8")
    log_file = tmp_path / ".pytest_logs" / "test.py.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("log", encoding="utf-8")

    monkeypatch.setattr(parsers, "get_coverage_annotation_path", lambda p: tmp_path / "nonexistent")
    import unittest.mock
    with unittest.mock.patch("coding_tools.parsers.get_pytest_log_path", return_value=log_file):
        t, c, p = parsers.read_local_files(str(test_file), str(source_file), "prefix")
        assert "No coverage report built" in c


def test_run_preflight_compliance_and_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_file = tmp_path / "test_valid.py"
    test_file.write_text("# SPDX-License-Identifier: Apache-2.0\n\ndef test_something():\n    assert True\n    assert True\n    assert True\n    assert True\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    
    ok, errs = parsers.run_preflight_compliance_and_validation(str(test_file), "prefix")
    assert ok

    with monkeypatch.context() as m:
        m.setattr("coding_tools.parsers.WorkspaceStamper.run", lambda self: (_ for _ in ()).throw(Exception("fail")))
        try:
            raise ValueError("Error")
        except ValueError:
            ok2, _ = parsers.run_preflight_compliance_and_validation(str(test_file), "prefix")
            assert ok2


def test_run_preflight_compliance_and_validation_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    test_file = tmp_path / "test_invalid.py"
    test_file.write_text("def test_short(): pass\n", encoding="utf-8")
    ok, errs = parsers.run_preflight_compliance_and_validation(str(test_file), "prefix")
    assert not ok


def test_run_preflight_compliance_and_validation_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    ok, errs = parsers.run_preflight_compliance_and_validation(str(tmp_path / "nonexistent.py"), "prefix")
    assert not ok


def test_validate_llm_code() -> None:
    code = "# SPDX-License-Identifier: Apache-2.0\n\ndef test_a():\n    assert True\n    assert True\n    assert True\n    assert True\n"
    ok, _ = parsers.validate_llm_code(code)
    assert ok

    short_code = "print(1)"
    ok, _ = parsers.validate_llm_code(short_code)
    assert not ok

    no_comment = "\ndef test_a():\n    assert True\n    assert True\n    assert True\n    assert True\n"
    ok, _ = parsers.validate_llm_code(no_comment)
    assert not ok

    bad_syntax = "# SPDX-License-Identifier: Apache-2.0\n\ndef test_a(\n"
    ok, _ = parsers.validate_llm_code(bad_syntax)
    assert not ok

    bad_isolation = "# SPDX-License-Identifier: Apache-2.0\nwith open('/etc/passwd', 'r') as f:\n    pass\n"
    ok, _ = parsers.validate_llm_code(bad_isolation)
    assert not ok


def test_process_and_save_code(tmp_path: Path) -> None:
    test_file = tmp_path / "test_file.py"
    test_file.write_text("old code\n", encoding="utf-8")
    parsers.process_and_save_code("new code\n", str(test_file), "prefix")
    assert test_file.read_text(encoding="utf-8") == "new code\n"
