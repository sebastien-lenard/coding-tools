# tests/unit/test_llm_emcee.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for llm_emcee module."""

import asyncio
from pathlib import Path
from typing import Never

import pytest

from coding_tools import conf, my_io, my_path
from coding_tools.llm_emcee import (
    CheckParams,
    Context,
    _prepare_context_and_version,
    _safe_call_func,
    chat,
    run,
)
from coding_tools.llm_protocol import LLMCallParams, LLMResponse
from coding_tools.my_run import EditState, RunOutput, RunState


class MockLLMClient:
    """Mock LLM client for testing."""

    async def call(self, req: str, params: LLMCallParams) -> LLMResponse:
        """Call the mock LLM."""
        del req, params
        return LLMResponse(message="ok", edited_files="# edited")


class MockFailingLLMClient:
    """Mock failing LLM client for testing."""

    async def call(self, req: str, params: LLMCallParams) -> LLMResponse:
        """Call the mock LLM and fail."""
        del req, params
        msg = "LLM Failure"
        raise RuntimeError(msg)


def dummy_check(params: CheckParams, run_output: RunOutput) -> RunOutput:
    """Execute dummy check function that passes."""
    del params
    return RunOutput(
        func=run_output.func,
        status=RunState.PASS,
        edited=EditState.EDITED,
        input_path=run_output.input_path,
    )


def non_passing_check(params: CheckParams, run_output: RunOutput) -> RunOutput:
    """Execute dummy check function that fails."""
    del params
    return RunOutput(
        func=run_output.func,
        status=RunState.FAIL,
        edited=getattr(EditState, "UNEDITED", EditState.EDITED),
        input_path=run_output.input_path,
    )


def failing_check(params: CheckParams, run_output: RunOutput) -> Never:
    """Raise ValueError in dummy check function."""
    del params, run_output
    msg = "Check error"
    raise ValueError(msg)


def failing_precheck(params: CheckParams, run_output: RunOutput) -> Never:
    """Raise ValueError in dummy precheck function."""
    del params, run_output
    msg = "Precheck error"
    raise ValueError(msg)


def passing_precheck(params: CheckParams, run_output: RunOutput) -> RunOutput:
    """Execute dummy precheck function that passes."""
    del params
    return RunOutput(
        func=run_output.func,
        status=RunState.PASS,
        edited=EditState.EDITED,
        input_path=run_output.input_path,
    )


def test_chat_bad_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test chat with a bad file."""
    missing = tmp_path / "missing.py"
    monkeypatch.setattr(
        my_io,
        "read_txt",
        lambda p, header=False, raise_err=True: _raise_fn(),
    )
    monkeypatch.setattr(conf, "python_version", lambda p: "")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        check_func=dummy_check,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=missing)
    res = asyncio.run(chat(missing, ctx, ro))
    assert res.status == RunState.FAIL


def _raise_fn() -> str:
    msg = "Missing"
    raise RuntimeError(msg)


def test_chat_success_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test chat success flow."""
    f = tmp_path / "code.py"
    monkeypatch.setattr(
        my_io,
        "read_txt",
        lambda p, header=False, raise_err=True: "print('hi')",
    )
    monkeypatch.setattr(my_io, "write_txt", lambda txt, p, **kw: None)
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        check_func=dummy_check,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.PASS


def test_execute_chat_step_pass_below_min_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test chat step pass below min steps."""
    f = tmp_path / "code.py"
    f.write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    monkeypatch.setattr(my_io, "write_txt", lambda txt, p, **kw: None)
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        check_func=dummy_check,
        min_steps=2,
        max_steps=2,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.PASS


def test_run_parallel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test running parallel chats."""
    f1 = tmp_path / "code1.py"
    f2 = tmp_path / "code2.py"
    monkeypatch.setattr(
        my_io,
        "read_txt",
        lambda p, header=False, raise_err=True: "print('hi')",
    )
    monkeypatch.setattr(my_io, "write_txt", lambda txt, p, **kw: None)
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        check_func=dummy_check,
    )
    ros = [
        RunOutput(func="test", status=RunState.PRESTART, input_path=f1),
        RunOutput(func="test", status=RunState.PRESTART, input_path=f2),
    ]
    results = asyncio.run(run(ctx, ros))
    assert len(results) == 2


def test_safe_call_func_exception() -> None:
    """Test safe call function exception handling."""

    def bad_func(*args: object, **kwargs: object) -> Never:
        del args, kwargs
        msg = "fail"
        raise RuntimeError(msg)

    ro = RunOutput(func="test", status=RunState.PRESTART)
    res = _safe_call_func(bad_func, ro)
    assert isinstance(res, RuntimeError)


def test_prepare_context_and_version_unit_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test prepare context and version for unit tests."""
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_foo(): pass", encoding="utf-8")
    src_file = tmp_path / "sample.py"
    src_file.write_text("def foo(): pass", encoding="utf-8")

    monkeypatch.setattr(my_path, "is_unit_test", lambda p: True)
    monkeypatch.setattr(my_path, "src_path", lambda p: src_file)
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")

    async def run_prep() -> tuple[str, str]:
        return await _prepare_context_and_version(test_file)

    ctx_txt, _ver_str = asyncio.run(run_prep())
    assert "def foo()" in ctx_txt


def test_prepare_context_and_version_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test prepare context and version error."""
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_foo(): pass", encoding="utf-8")

    monkeypatch.setattr(my_path, "is_unit_test", lambda p: True)
    monkeypatch.setattr(
        my_path,
        "src_path",
        lambda p: tmp_path / "nonexistent.py",
    )
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    monkeypatch.setattr(
        my_io,
        "read_txt",
        lambda p, header=False, raise_err=True: (_ for _ in ()).throw(
            OSError("Missing"),
        ),
    )

    async def run_prep() -> tuple[str, str]:
        return await _prepare_context_and_version(test_file)

    with pytest.raises(OSError, match="Missing"):
        asyncio.run(run_prep())


def test_chat_prepare_context_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test chat prepare context OS error."""
    f = tmp_path / "test_code.py"
    f.write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(my_path, "is_unit_test", lambda p: True)
    monkeypatch.setattr(
        my_path,
        "src_path",
        lambda p: tmp_path / "nonexistent.py",
    )
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")

    orig_read = my_io.read_txt

    def mock_read(p: Path | str, header: bool = False, raise_err: bool = True) -> str:
        if "nonexistent.py" in str(p):
            msg = "OS Error"
            raise OSError(msg)
        return orig_read(p, header=header, raise_err=raise_err)

    monkeypatch.setattr(my_io, "read_txt", mock_read)
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.FAIL


def test_execute_chat_step_precheck_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test execute chat step precheck error."""
    f = tmp_path / "code.py"
    f.write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        check_func=failing_check,
        min_steps=1,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.FAIL


def test_execute_chat_step_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test execute chat step exception."""
    f = tmp_path / "code.py"
    f.write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockFailingLLMClient(),
        check_func=dummy_check,
        min_steps=1,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.FAIL


def test_chat_precheck_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test chat precheck error."""
    f = tmp_path / "code.py"
    f.write_text("print('hi')", encoding="utf-8")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        precheck_func=failing_precheck,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.FAIL


def test_chat_precheck_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test chat precheck pass."""
    f = tmp_path / "code.py"
    f.write_text("print('hi')", encoding="utf-8")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        precheck_func=passing_precheck,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.PASS


def test_chat_prepare_context_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test chat prepare context error."""
    f = tmp_path / "test_code.py"
    f.write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(my_path, "is_unit_test", lambda p: True)
    monkeypatch.setattr(
        my_path,
        "src_path",
        lambda p: tmp_path / "nonexistent.py",
    )
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    monkeypatch.setattr(
        my_io,
        "read_txt",
        lambda p, header=False, raise_err=True: (_ for _ in ()).throw(
            RuntimeError("Missing"),
        ),
    )
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.FAIL


def test_execute_chat_step_non_passing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test execute chat step non passing."""
    f = tmp_path / "code.py"
    f.write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(conf, "python_version", lambda p: "3.12")
    ctx = Context(
        func_name="test",
        root_dir=tmp_path,
        llm=MockLLMClient(),
        check_func=non_passing_check,
        min_steps=1,
    )
    ro = RunOutput(func="test", status=RunState.PRESTART, input_path=f)
    res = asyncio.run(chat(f, ctx, ro))
    assert res.status == RunState.FAIL
