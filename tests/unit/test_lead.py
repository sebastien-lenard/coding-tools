# tests/unit/test_lead.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for lead module."""

import argparse
import asyncio
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Never, cast

import pytest

from coding_tools import lead
from coding_tools.my_run import RunOutput, RunState

if TYPE_CHECKING:
    from typing import Any

    DummyModule = Any
else:
    DummyModule = ModuleType


def test_context_missing_conftest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test context raises RuntimeError when conftest.py is missing."""
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "src" / "my_mod"
    sub.mkdir(parents=True)
    target = sub / "file.py"
    target.write_text("pass", encoding="utf-8")

    monkeypatch.setitem(
        lead.TOOLS,
        "my-tool",
        {"mod": "coding_tools.my_path", "llm": "False"},
    )

    args = argparse.Namespace(tool="my-tool", path=str(target), test=True)
    with pytest.raises(RuntimeError, match=r"Missing tests\\conftest.py"):
        lead.context(args)


def test_context_bad_tool() -> None:
    """Test context raises ValueError on bad tool."""
    args = argparse.Namespace(tool="non-existent", path="/some/path", test=False)
    with pytest.raises(ValueError, match="Bad tool: non-existent"):
        lead.context(args)


def test_context_bad_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test context raises RuntimeError on failed import."""
    monkeypatch.setitem(
        lead.TOOLS,
        "bad-import",
        {"mod": "coding_tools.non_existent_module", "llm": "False"},
    )
    args = argparse.Namespace(tool="bad-import", path=str(tmp_path), test=False)
    with pytest.raises(RuntimeError, match="Failed import of"):
        lead.context(args)


def test_context_missing_input_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test context raises FileNotFoundError on missing files."""
    monkeypatch.setitem(
        lead.TOOLS,
        "my-tool",
        {"mod": "coding_tools.my_path", "llm": "False"},
    )
    args = argparse.Namespace(
        tool="my-tool",
        path=str(tmp_path / "missing"),
        test=False,
    )
    with pytest.raises(FileNotFoundError, match="Missing input files at"):
        lead.context(args)


def test_context_llm_missing_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test context raises RuntimeError when LLM skill or template is missing."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.py"
    target.write_text("pass", encoding="utf-8")
    monkeypatch.setitem(
        lead.TOOLS,
        "llm-tool",
        {"mod": "coding_tools.my_path", "llm": "True"},
    )
    args = argparse.Namespace(tool="llm-tool", path=str(target), test=False)
    with pytest.raises(RuntimeError, match="Missing skill at"):
        lead.context(args)


def test_context_llm_missing_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test context raises RuntimeError when LLM template is missing."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.py"
    target.write_text(
        "pass",
        encoding="utf-8",
    )
    skill_file = tmp_path / "conf" / "skills" / "llm_tool.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("skill", encoding="utf-8")

    monkeypatch.setitem(
        lead.TOOLS,
        "llm-tool",
        {"mod": "coding_tools.my_path", "llm": "True"},
    )
    args = argparse.Namespace(tool="llm-tool", path=str(target), test=False)
    with pytest.raises(RuntimeError, match="Missing template at"):
        lead.context(args)


def test_parse_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parse_args correctly parses command line arguments."""
    monkeypatch.setattr("sys.argv", ["lead.py", "my-tool", "some/path", "--test"])
    parsed = lead.parse_args()
    assert parsed.tool == "my-tool"
    assert parsed.path == "some/path"
    assert parsed.test is True


def test_run_exception_handling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test lead run handles exceptions and exits with 1."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.py"
    target.write_text("pass", encoding="utf-8")

    monkeypatch.setattr(
        lead,
        "parse_args",
        lambda: argparse.Namespace(
            tool="my-tool",
            path=str(target),
            test=False,
        ),
    )

    dummy_mod = cast("DummyModule", ModuleType("dummy_mod"))
    dummy_mod.check = lambda *a, **kw: None
    dummy_mod.precheck = lambda *a, **kw: None
    dummy_mod.MIN_STEPS = 1
    dummy_mod.MAX_STEPS = 5
    sys.modules["coding_tools.dummy_mod"] = dummy_mod
    monkeypatch.setitem(
        lead.TOOLS,
        "my-tool",
        {"mod": "coding_tools.dummy_mod", "llm": "False"},
    )

    async def mock_llm_run_error(ctx: lead.Context, outputs: list[RunOutput]) -> Never:
        msg = "API Fail"
        raise lead.LLMAPIError(msg)

    monkeypatch.setattr(lead.llm_emcee, "run", mock_llm_run_error)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(lead.run())
    assert exc_info.value.code == 1


def test_run_context_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test lead run catches context exceptions and exits."""
    monkeypatch.setattr(
        lead,
        "parse_args",
        lambda: argparse.Namespace(
            tool="bad",
            path="",
            test=False,
        ),
    )
    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(lead.run())
    assert exc_info.value.code == 1


def test_run_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test lead run success."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.py"
    target.write_text("pass", encoding="utf-8")

    monkeypatch.setitem(
        lead.TOOLS,
        "my-tool",
        {"mod": "coding_tools.my_path", "llm": "False"},
    )
    monkeypatch.setattr(
        lead,
        "parse_args",
        lambda: argparse.Namespace(
            tool="my-tool",
            path=str(target),
            test=False,
        ),
    )

    dummy_mod = cast("DummyModule", ModuleType("dummy_mod"))
    dummy_mod.check = lambda *a, **kw: None
    dummy_mod.precheck = lambda *a, **kw: None
    dummy_mod.MIN_STEPS = 1
    dummy_mod.MAX_STEPS = 5
    sys.modules["coding_tools.dummy_mod"] = dummy_mod
    monkeypatch.setitem(
        lead.TOOLS,
        "my-tool",
        {"mod": "coding_tools.dummy_mod", "llm": "False"},
    )

    async def mock_llm_run(
        ctx: lead.Context, outputs: list[RunOutput],
    ) -> list[RunOutput]:
        outputs[0].status = RunState.PASS
        outputs[0].input_path = None
        outputs[0].output_path = tmp_path / "file.py"
        return outputs

    monkeypatch.setattr(lead.llm_emcee, "run", mock_llm_run)

    asyncio.run(lead.run())


def test_main_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the main execution entry block."""
    monkeypatch.setattr(
        lead,
        "parse_args",
        lambda: argparse.Namespace(
            tool="bad",
            path="",
            test=False,
        ),
    )
    with pytest.raises(SystemExit):
        lead.main()
