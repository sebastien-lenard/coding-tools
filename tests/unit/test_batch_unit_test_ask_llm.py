# tests/unit/test_batch_unit_test_ask_llm.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for batch_unit_test_ask_llm module."""

from __future__ import annotations

import asyncio
import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from coding_tools import batch_unit_test_ask_llm as butag

if TYPE_CHECKING:
    from collections.abc import Coroutine


@pytest.mark.parametrize(
    ("source_file", "expected"),
    [
        (
            "src/coding_tools/providers/toto.py",
            str(Path("tests/unit/providers/test_toto.py")),
        ),
        ("src/foo.py", str(Path("tests/unit/test_foo.py"))),
        ("foo.py", str(Path("tests/unit/test_foo.py"))),
        ("bar/baz/qux.py", str(Path("tests/unit/test_qux.py"))),
        (
            "/absolute/path/src/module/sub/file.py",
            str(Path("tests/unit/sub/test_file.py")),
        ),
    ],
)
def test_get_test_file_path(source_file: str, expected: str) -> None:
    """Test resolving test file paths from source file paths."""
    assert butag.get_test_file_path(source_file) == expected


def test_ensure_test_file_exists(tmp_path: Path) -> None:
    """Test ensuring test files and directories exist."""
    test_file = tmp_path / "nested" / "test_sample.py"
    assert not test_file.exists()
    butag.ensure_test_file_exists(str(test_file))
    assert test_file.exists()
    butag.ensure_test_file_exists(str(test_file))
    assert test_file.exists()


@pytest.mark.anyio
async def test_run_workflow_with_iterations_success() -> None:
    """Test successful workflow execution on first iteration."""
    with patch(
        "coding_tools.batch_unit_test_ask_llm.execute_workflow",
        return_value=(True, "All Stages", "Success"),
    ) as mock_exec:
        result = await butag.run_workflow_with_iterations(
            "tests/unit/test_dummy.py", "src/dummy.py", max_iterations=3,
        )
        assert result == {
            "test_file": "tests/unit/test_dummy.py",
            "stage": "All Stages",
            "status": "Success",
            "iterations": 1,
        }
        assert mock_exec.call_count == 1


@pytest.mark.anyio
async def test_run_workflow_with_iterations_no_llm_fix() -> None:
    """Test workflow execution stopping on 'No LLM fix' status."""
    with patch(
        "coding_tools.batch_unit_test_ask_llm.execute_workflow",
        return_value=(False, "Pytest/Coverage", "No LLM fix"),
    ) as mock_exec:
        result = await butag.run_workflow_with_iterations(
            "tests/unit/test_dummy.py", "src/dummy.py", max_iterations=3,
        )
        assert result == {
            "test_file": "tests/unit/test_dummy.py",
            "stage": "Pytest/Coverage",
            "status": "No LLM fix",
            "iterations": 1,
        }
        assert mock_exec.call_count == 1


@pytest.mark.anyio
async def test_run_workflow_with_iterations_fixed() -> None:
    """Test workflow execution with Fixed status followed by success."""
    with patch(
        "coding_tools.batch_unit_test_ask_llm.execute_workflow",
        side_effect=[
            (False, "Pytest/Coverage", "Fixed"),
            (True, "All Stages", "Success"),
        ],
    ) as mock_exec:
        result = await butag.run_workflow_with_iterations(
            "tests/unit/test_dummy.py", "src/dummy.py", max_iterations=3,
        )
        assert result == {
            "test_file": "tests/unit/test_dummy.py",
            "stage": "All Stages",
            "status": "Success",
            "iterations": 2,
        }
        assert mock_exec.call_count == 2


@pytest.mark.anyio
async def test_run_workflow_with_iterations_warning_then_no_gemini() -> None:
    """Test workflow execution with warning status when allow_gemini is False."""
    with patch(
        "coding_tools.batch_unit_test_ask_llm.execute_workflow",
        return_value=(False, "Pytest/Coverage", "WarningState"),
    ) as mock_exec:
        result = await butag.run_workflow_with_iterations(
            "tests/unit/test_dummy.py", "src/dummy.py", max_iterations=1,
        )
        assert result == {
            "test_file": "tests/unit/test_dummy.py",
            "stage": "Pytest/Coverage",
            "status": "WarningState",
            "iterations": 1,
        }
        assert mock_exec.call_count == 1


@pytest.mark.anyio
async def test_run_workflow_with_iterations_exhausted() -> None:
    """Test workflow execution exhausting max iterations."""
    with patch(
        "coding_tools.batch_unit_test_ask_llm.execute_workflow",
        return_value=(False, "Pytest/Coverage", "FAILED"),
    ) as mock_exec:
        result = await butag.run_workflow_with_iterations(
            "tests/unit/test_dummy.py", "src/dummy.py", max_iterations=2,
        )
        assert result == {
            "test_file": "tests/unit/test_dummy.py",
            "stage": "Pytest/Coverage",
            "status": "FAILED",
            "iterations": 2,
        }
        assert mock_exec.call_count == 2


@pytest.mark.anyio
async def test_run_workflow_with_iterations_exception() -> None:
    """Test workflow execution handling exceptions properly."""
    with patch(
        "coding_tools.batch_unit_test_ask_llm.execute_workflow",
        side_effect=RuntimeError("Boom"),
    ):
        result = await butag.run_workflow_with_iterations(
            "tests/unit/test_dummy.py", "src/dummy.py", max_iterations=2,
        )
        assert result == {
            "test_file": "tests/unit/test_dummy.py",
            "stage": "Pytest/Coverage",
            "status": "Error",
            "iterations": 1,
        }


@pytest.mark.anyio
async def test_run_workflow_with_semaphore() -> None:
    """Test workflow execution using an asyncio semaphore."""
    semaphore = asyncio.Semaphore(1)
    with patch(
        "coding_tools.batch_unit_test_ask_llm.execute_workflow",
        return_value=(True, "All Stages", "Success"),
    ):
        result = await butag.run_workflow_with_iterations(
            "tests/unit/test_dummy.py",
            "src/dummy.py",
            max_iterations=1,
            semaphore=semaphore,
        )
        assert result["status"] == "Success"


def test_print_summary_table(caplog: pytest.LogCaptureFixture) -> None:
    """Test printing summary table for workflow results."""
    results = [
        {
            "test_file": "tests/unit/test_a.py",
            "stage": "All Stages",
            "status": "Success",
            "iterations": 1,
        },
    ]
    with caplog.at_level("INFO"):
        butag.print_summary_table(results, processed_multiple=False)
    assert any(
        "Unit test writing (file) Summary" in record.message
        for record in caplog.records
    )
    assert any("tests/unit/test_a.py" in record.message for record in caplog.records)


def test_print_summary_table_multiple(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test summary table output with multiple files."""
    results = [
        {
            "test_file": "tests/unit/test_a.py",
            "stage": "Pytest/Coverage",
            "status": "FAILED",
            "iterations": 5,
        },
    ]
    with caplog.at_level("INFO"):
        butag.print_summary_table(results, processed_multiple=True)
    assert any(
        "Unit test writing (batch) Summary:" in record.message
        for record in caplog.records
    )


def test_main_file_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main entry point with a single file target."""
    monkeypatch.chdir(tmp_path)
    py_file = tmp_path / "src" / "coding_tools" / "sample.py"
    py_file.parent.mkdir(parents=True, exist_ok=True)
    py_file.write_text("print('hello')", encoding="utf-8")

    test_file_str = butag.get_test_file_path(str(py_file))

    with patch("sys.argv", ["batch_unit_test_ask_llm.py", str(py_file)]), patch(
        "coding_tools.batch_unit_test_ask_llm.run_workflow_with_iterations",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = {
            "test_file": test_file_str,
            "stage": "All Stages",
            "status": "Success",
            "iterations": 1,
        }
        butag.main()
        mock_run.assert_awaited_once()


def test_main_invalid_file_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main entry point with an invalid non-python file target."""
    monkeypatch.chdir(tmp_path)
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("hello", encoding="utf-8")

    with patch("sys.argv", ["batch_unit_test_ask_llm.py", str(txt_file)]):
        butag.main()


def test_main_nonexistent_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main entry point with a nonexistent path target."""
    monkeypatch.chdir(tmp_path)
    with patch(
        "sys.argv", ["batch_unit_test_ask_llm.py", "nonexistent_path_abc_123"],
    ):
        butag.main()


def test_main_dir_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test main entry point with a directory target."""
    monkeypatch.chdir(tmp_path)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    py_file = src_dir / "sample.py"
    py_file.write_text("print('hello')", encoding="utf-8")
    init_file = src_dir / "__init__.py"
    init_file.write_text("", encoding="utf-8")

    with patch("sys.argv", ["batch_unit_test_ask_llm.py", str(tmp_path)]), patch(
        "coding_tools.batch_unit_test_ask_llm.run_workflow_with_iterations",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = {
            "test_file": "tests/unit/test_sample.py",
            "stage": "All Stages",
            "status": "Success",
            "iterations": 1,
        }
        butag.main()
        mock_run.assert_awaited()


def test_if_name_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test module execution block if __name__ == '__main__':."""
    monkeypatch.chdir(tmp_path)
    def mock_run(coro: Coroutine[Any, Any, Any]) -> None:
        coro.close()

    with (
        patch("asyncio.run", side_effect=mock_run),
        patch("sys.argv", ["batch_unit_test_ask_llm.py"]),
    ):
        ws_module = sys.modules[butag.__name__]
        assert ws_module.__file__ is not None, "Module file path cannot be None"
        target_file_path = str(Path(ws_module.__file__).resolve())
        runpy.run_path(target_file_path, run_name="__main__")
