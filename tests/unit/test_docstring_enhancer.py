# tests/unit/test_docstring_enhancer.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for docstring_enhancer module."""

import ast
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from coding_tools.docstring_enhancer import (
    _run_enhancement_pass,
    _strip_docstrings,
    async_main,
    main,
    print_summary_table,
    process_file_workflow,
    validate_docstring_mutations,
)
from coding_tools.llm_protocol import LLMResponse, StructuredGenerationOptions


def test_strip_docstrings() -> None:
    """Test stripping docstrings from AST."""
    code = '''
"""Module docstring"""
class MyClass:
    """Class docstring"""
    def my_func(self) -> None:
        """Func docstring"""
        pass

    async def my_async_func(self) -> None:
        """Async func docstring"""
        pass
'''
    tree = ast.parse(code)
    _strip_docstrings(tree)
    unparsed = ast.unparse(tree)
    assert "Module docstring" not in unparsed
    assert "Class docstring" not in unparsed
    assert "Func docstring" not in unparsed
    assert "Async func docstring" not in unparsed


def test_validate_docstring_mutations_syntax_error() -> None:
    """Test validation catches syntax errors in mutations."""
    orig = "def foo(): pass"
    new = "def foo(: pass"
    valid, reason = validate_docstring_mutations(orig, new, "test")
    assert not valid
    assert "Bad code syntax" in reason


def test_validate_docstring_mutations_too_long() -> None:
    """Test validation catches too long docstrings."""
    orig = "def foo(): pass"
    new = (
        'def foo():\n    '
        '"""Line1\n    Line2\n    Line3\n    '
        'Line4\n    Line5\n    Line6\n    '
        'Line7\n    Line8\n    Line9\n    '
        'Line10\n    Line11"""\n    pass'
    )
    valid, reason = validate_docstring_mutations(orig, new, "test")
    assert not valid
    assert "Docstring lines:" in reason


def test_validate_docstring_mutations_code_modified() -> None:
    """Test validation catches modified code structures."""
    orig = "def foo(): pass"
    new = "def foo(): return 1"
    valid, reason = validate_docstring_mutations(orig, new, "test")
    assert not valid
    assert "Spotted code edits" in reason


def test_validate_docstring_mutations_success() -> None:
    """Test successful docstring mutation validation."""
    orig = "def foo(): pass"
    new = 'def foo():\n    """Docstring."""\n    pass'
    valid, reason = validate_docstring_mutations(orig, new, "test")
    assert valid
    assert reason == "OK"


def test_run_enhancement_pass_success_first_try() -> None:
    """Test enhancement pass succeeds on the first try."""
    client = MagicMock()
    client.generate_structured_response.return_value = LLMResponse(
        message="Success",
        code='def foo():\n    """Doc."""\n    pass',
    )
    options = StructuredGenerationOptions(
        response_schema=LLMResponse,
        prefix="test",
        spinner_msg="spinner",
        system_instruction="instr",
    )
    original_code = "def foo(): pass"
    success, result_code = asyncio.run(
        _run_enhancement_pass(
            client,
            ["content"],
            options,
            original_code,
            "test",
        ),
    )
    assert success
    assert '"""Doc."""' in result_code


def test_run_enhancement_pass_success_second_try() -> None:
    """Test enhancement pass succeeds on the second try."""
    client = MagicMock()
    client.generate_structured_response.side_effect = [
        LLMResponse(message="Retry", code="def foo(): return 2"),
        LLMResponse(
            message="Success",
            code='def foo():\n    """Doc."""\n    pass',
        ),
    ]
    options = StructuredGenerationOptions(
        response_schema=LLMResponse,
        prefix="test",
        spinner_msg="spinner",
        system_instruction="instr",
    )
    original_code = "def foo(): pass"
    success, result_code = asyncio.run(
        _run_enhancement_pass(
            client,
            ["content"],
            options,
            original_code,
            "test",
        ),
    )
    assert success
    assert '"""Doc."""' in result_code
    assert client.generate_structured_response.call_count == 2


def test_run_enhancement_pass_fail_both_tries() -> None:
    """Test enhancement pass fails when both tries fail."""
    client = MagicMock()
    client.generate_structured_response.return_value = LLMResponse(
        message="Fail",
        code="def foo(): return 2",
    )
    options = StructuredGenerationOptions(
        response_schema=LLMResponse,
        prefix="test",
        spinner_msg="spinner",
        system_instruction="instr",
    )
    original_code = "def foo(): pass"
    success, result_code = asyncio.run(
        _run_enhancement_pass(
            client,
            ["content"],
            options,
            original_code,
            "test",
        ),
    )
    assert not success
    assert result_code == original_code


def test_run_enhancement_pass_exception() -> None:
    """Test enhancement pass handles exceptions gracefully."""
    client = MagicMock()
    client.generate_structured_response.side_effect = Exception("API Error")
    options = StructuredGenerationOptions(
        response_schema=LLMResponse,
        prefix="test",
        spinner_msg="spinner",
        system_instruction="instr",
    )
    original_code = "def foo(): pass"
    success, result_code = asyncio.run(
        _run_enhancement_pass(
            client,
            ["content"],
            options,
            original_code,
            "test",
        ),
    )
    assert not success
    assert result_code == original_code


@patch("coding_tools.docstring_enhancer.get_llm_client")
@patch("coding_tools.docstring_enhancer.load_skill", return_value="skill")
@patch("coding_tools.docstring_enhancer.WorkspaceStamper")
def test_process_file_workflow_success(
    mock_stamper: MagicMock,
    mock_load_skill: MagicMock,
    mock_get_client: MagicMock,
    tmp_path: Path,
) -> None:
    """Test successful file processing workflow."""
    p = tmp_path / "sample.py"
    p.write_text("def foo(): pass", encoding="utf-8")
    client = MagicMock()
    client.generate_structured_response.return_value = LLMResponse(
        message="Success",
        code='def foo():\n    """Enhanced."""\n    pass',
    )
    mock_get_client.return_value = client
    semaphore = asyncio.Semaphore(1)
    res = asyncio.run(process_file_workflow(p, semaphore, "26-01-01"))
    assert res["status"] == "SUCCESS"
    assert "Enhanced." in p.read_text(encoding="utf-8")
    mock_stamper.return_value.run.assert_called_once()


@patch("coding_tools.docstring_enhancer.get_llm_client")
@patch("coding_tools.docstring_enhancer.load_skill", return_value="skill")
def test_process_file_workflow_pass1_fail(
    mock_load_skill: MagicMock,
    mock_get_client: MagicMock,
    tmp_path: Path,
) -> None:
    """Test file processing workflow when pass 1 fails."""
    p = tmp_path / "sample.py"
    p.write_text("def foo(): pass", encoding="utf-8")
    client = MagicMock()
    client.generate_structured_response.return_value = LLMResponse(
        message="Bad",
        code="def foo(): return bad",
    )
    mock_get_client.return_value = client
    semaphore = asyncio.Semaphore(1)
    res = asyncio.run(process_file_workflow(p, semaphore, "26-01-01"))
    assert res["status"] == "Failed"
    assert res["stage"] == "Step 1: Enhancement"


@patch("coding_tools.docstring_enhancer.get_llm_client")
@patch("coding_tools.docstring_enhancer.load_skill", return_value="skill")
@patch("coding_tools.docstring_enhancer.WorkspaceStamper")
def test_process_file_workflow_pass2_fail_fallback(
    mock_stamper: MagicMock,
    mock_load_skill: MagicMock,
    mock_get_client: MagicMock,
    tmp_path: Path,
) -> None:
    """Test file processing workflow falls back on pass 2 failure."""
    p = tmp_path / "sample.py"
    p.write_text("def foo(): pass", encoding="utf-8")
    client = MagicMock()
    client.generate_structured_response.side_effect = [
        LLMResponse(
            message="Pass1",
            code='def foo():\n    """Pass1."""\n    pass',
        ),
        LLMResponse(message="Pass2Fail", code="def invalid_pass2()"),
        LLMResponse(message="Pass2Fail", code="def invalid_pass2()"),
    ]
    mock_get_client.return_value = client
    semaphore = asyncio.Semaphore(1)
    res = asyncio.run(process_file_workflow(p, semaphore, "26-01-01"))
    assert res["status"] == "SUCCESS"
    assert "Pass1." in p.read_text(encoding="utf-8")


@patch("coding_tools.docstring_enhancer.WorkspaceStamper")
@patch("coding_tools.docstring_enhancer.get_llm_client")
@patch("coding_tools.docstring_enhancer.load_skill", return_value="skill")
def test_process_file_workflow_stamper_exception(
    mock_load_skill: MagicMock,
    mock_get_client: MagicMock,
    mock_stamper: MagicMock,
    tmp_path: Path,
) -> None:
    """Test file processing workflow handles stamper exceptions."""
    p = tmp_path / "sample.py"
    p.write_text("def foo(): pass", encoding="utf-8")
    client = MagicMock()
    client.generate_structured_response.return_value = LLMResponse(
        message="Success",
        code='def foo():\n    """Enhanced."""\n    pass',
    )
    mock_get_client.return_value = client
    mock_stamper.return_value.run.side_effect = Exception(
        "Stamper error",
    )
    semaphore = asyncio.Semaphore(1)
    res = asyncio.run(process_file_workflow(p, semaphore, "26-01-01"))
    assert res["status"] == "SUCCESS"


def test_print_summary_table(tmp_path: Path) -> None:
    """Test printing the summary table."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    f1 = sub / "file1.py"
    f2 = Path("absolute_outside_path.py")
    results = [
        {"file": str(f1), "status": "SUCCESS", "stage": "Completed"},
        {"file": str(f2), "status": "FAILED", "stage" : "Pass 1: Enhancement"},
    ]
    print_summary_table(results, tmp_path)


def test_async_main_target_not_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test async_main raises exit when target does not exist."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["docstring_enhancer.py", str(tmp_path / "nonexistent.py")],
    )
    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(async_main())
    assert exc_info.value.code == 1


def test_async_main_no_python_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test async_main exits when no python files are found."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["docstring_enhancer.py", str(empty_dir)],
    )
    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(async_main())
    assert exc_info.value.code == 1


@patch("coding_tools.docstring_enhancer.process_file_workflow")
def test_async_main_success_file(
    mock_process: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test async_main successfully processes a single file."""
    p = tmp_path / "sample.py"
    p.write_text("def foo(): pass", encoding="utf-8")

    async def mock_workflow(
        *args: object,
        **kwargs: object,
    ) -> dict[str, str]:
        """Mock workflow."""
        return {"file": str(p), "status": "SUCCESS", "stage": "Completed"}

    mock_process.side_effect = mock_workflow
    monkeypatch.setattr(sys, "argv", ["docstring_enhancer.py", str(p)])
    asyncio.run(async_main())
    mock_process.assert_called_once()


@patch("coding_tools.docstring_enhancer.process_file_workflow")
def test_async_main_success_dir(
    mock_process: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test async_main successfully processes a directory."""
    p = tmp_path / "sample.py"
    p.write_text("def foo(): pass", encoding="utf-8")

    async def mock_workflow(
        *args: object,
        **kwargs: object,
    ) -> dict[str, str]:
        """Mock workflow."""
        return {"file": str(p), "status": "SUCCESS", "stage": "Completed"}

    mock_process.side_effect = mock_workflow
    monkeypatch.setattr(sys, "argv", ["docstring_enhancer.py", str(tmp_path)])
    asyncio.run(async_main())
    mock_process.assert_called_once()


def test_main_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main CLI entry point."""
    with patch(
        "coding_tools.docstring_enhancer.async_main",
    ) as mock_async_main:
        mock_async_main.return_value = None
        main()
        mock_async_main.assert_called_once()
