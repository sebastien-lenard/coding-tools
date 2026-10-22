# tests/unit/test_function_signatures_dependencies.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for coding_tools.function_signatures_dependencies."""

import ast
import runpy
import sys
from pathlib import Path
from typing import Never

import pytest

from coding_tools import function_signatures_dependencies as fsd
from coding_tools.function_signatures_dependencies import (
    CodeStructureAnalyzer,
)


def test_target_output_path(tmp_path: Path) -> None:
    """Test target output path generation."""
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()

    analyzer1 = CodeStructureAnalyzer(project_path=project_dir)
    assert analyzer1.target_output_path == project_dir / "my_project_structure.md"

    custom_out = tmp_path / "custom.md"
    analyzer2 = CodeStructureAnalyzer(project_path=project_dir, output_file=custom_out)
    assert analyzer2.target_output_path == custom_out


def test_execute_missing_src(tmp_path: Path) -> None:
    """Test execute behavior when src directory is missing."""
    analyzer = CodeStructureAnalyzer(project_path=tmp_path)
    assert analyzer.execute() == 1


def test_execute_no_modules(tmp_path: Path) -> None:
    """Test execute behavior when no modules are present."""
    src = tmp_path / "src"
    src.mkdir()
    analyzer = CodeStructureAnalyzer(project_path=tmp_path)
    assert analyzer.execute() == 1


def test_execute_parse_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test execute behavior on parse error."""
    src = tmp_path / "src"
    src.mkdir()
    py_file = src / "bad.py"
    py_file.write_text("invalid python syntax +++", encoding="utf-8")

    analyzer = CodeStructureAnalyzer(project_path=tmp_path)
    assert analyzer.execute() == 1
    assert "Failed to parse AST" in caplog.text


def test_execute_write_error(tmp_path: Path) -> None:
    """Test execute behavior on write error."""
    src = tmp_path / "src"
    src.mkdir()
    py_file = src / "mod.py"
    py_file.write_text("x = 1", encoding="utf-8")

    out_dir = tmp_path / "outdir"
    out_dir.mkdir()

    analyzer = CodeStructureAnalyzer(project_path=tmp_path, output_file=out_dir)
    assert analyzer.execute() == 1


def test_comprehensive_analysis(tmp_path: Path) -> None:
    """Test comprehensive structure analysis across multiple modules."""
    project_dir = tmp_path / "test_proj"
    src_dir = project_dir / "src"
    sub_dir = src_dir / "sub"
    sub_dir.mkdir(parents=True)

    pycache = src_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "ignored.py").write_text("x = 1", encoding="utf-8")

    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text('[project]\nname = "test_proj"', encoding="utf-8")

    mod1_code = '''"""Module 1 docstring.\n\n    Multi-paragraph description.\n    """
import os
import sys
import external_module
from pathlib import Path
from . import relative_mod
from .sub import helper

CONSTANT_STR = "hello"
CONSTANT_UNASSIGNED: int
CONSTANT_COMPLEX = 1 + 2
CONSTANT_ANN: int = 10

@decorator1
class BaseClass:
    pass

@decorator2
class MyClass(BaseClass):
    """Class docstring.\n\n    Class multi-paragraph docstring.\n    """
    def __init__(self):
        """Init docstring.\n\n        Init multi-paragraph docstring.\n        """
        helper()
        helper() # duplicate call

    async def async_method(self) -> int:
        raise ValueError("error in async")
        raise ValueError("error in async") # duplicate raise
        return 0

@dec_func
def standalone_func(a: int) -> str:
    if a > 0:
        raise RuntimeError("positive error")
    try:
        raise TypeError("caught error")
    except TypeError:
        pass
    return standalone_func_inner(a)

def standalone_func_inner(a: int):
    raise
    return str(a)

def bare_func():
    pass
'''
    (src_dir / "mod1.py").write_text(mod1_code, encoding="utf-8")
    (src_dir / "relative_mod.py").write_text("def foo(): pass", encoding="utf-8")
    (sub_dir / "helper.py").write_text(
        "def helper(): pass\ndef target_func(): pass",
        encoding="utf-8",
    )
    (src_dir / "mod_dep.py").write_text(
        "from test_proj.src import mod1\ndef dep_func(): pass",
        encoding="utf-8",
    )

    analyzer = CodeStructureAnalyzer(project_path=project_dir)
    success = analyzer.execute()
    assert success == 0

    output_path = analyzer.target_output_path
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "Module 1 docstring" in content
    assert "BaseClass" in content
    assert "MyClass" in content
    assert "standalone_func" in content
    assert "pyproject.toml" in content


def test_comprehensive_analysis_no_pyproject(tmp_path: Path) -> None:
    """Test analysis when pyproject.toml is absent."""
    project_dir = tmp_path / "test_proj_no_pyproj"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "mod.py").write_text("x = 1", encoding="utf-8")

    analyzer = CodeStructureAnalyzer(project_path=project_dir)
    assert analyzer.execute() == 0


def test_pyproject_is_directory(tmp_path: Path) -> None:
    """Test analysis when pyproject.toml is a directory instead of file."""
    project_dir = tmp_path / "proj_dir_toml"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "mod.py").write_text("x = 1", encoding="utf-8")
    (project_dir / "pyproject.toml").mkdir()

    analyzer = CodeStructureAnalyzer(project_path=project_dir)
    assert analyzer.execute() == 0


def test_class_variants(tmp_path: Path) -> None:
    """Test class without docstring and with bases/decorators."""
    project_dir = tmp_path / "proj"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    code = """
@dec
class SimpleClass:
    def method(self):
        pass
"""
    (src_dir / "mod.py").write_text(code, encoding="utf-8")
    analyzer = CodeStructureAnalyzer(project_path=project_dir)
    assert analyzer.execute() == 0


def test_oserror_handling_in_unparse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handling of OSError during unparse operations."""
    src = tmp_path / "src"
    src.mkdir()
    py_file = src / "mod.py"
    py_file.write_text("x = 1\ny: int = 2", encoding="utf-8")

    original_unparse = ast.unparse
    def mock_unparse(node: ast.AST) -> str:
        if isinstance(node, ast.Constant) and node.value in (1, 2):
            msg = "disk error"
            raise OSError(msg)
        return original_unparse(node)

    monkeypatch.setattr(ast, "unparse", mock_unparse)

    analyzer = CodeStructureAnalyzer(project_path=tmp_path)
    success = analyzer.execute()
    assert success == 0
    content = analyzer.target_output_path.read_text(encoding="utf-8")
    assert "<complex>" in content or "<expr>" in content


def test_safe_unparse_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test safe fallback when unparse raises OSError."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def foo(): pass", encoding="utf-8")

    def mock_unparse(node: ast.AST) -> Never:
        msg = "unparse fail"
        raise OSError(msg)

    monkeypatch.setattr(ast, "unparse", mock_unparse)
    analyzer = CodeStructureAnalyzer(project_path=tmp_path)
    modules = analyzer._analyze_modules()
    assert len(modules) == 1


def test_nested_try_exception(tmp_path: Path) -> None:
    """Test module dependency graph and nested try/except exception detection."""
    project_dir = tmp_path / "graph_proj"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)

    (src_dir / "mod_a.py").write_text("""
import sys
from graph_proj.src import mod_b
def func_a():
    try:
        try:
            raise ValueError("inner")
        except ValueError:
            raise TypeError("outer")
    except TypeError:
        pass
""", encoding="utf-8")

    (src_dir / "mod_b.py").write_text("def func_b(): pass", encoding="utf-8")

    analyzer = CodeStructureAnalyzer(project_path=project_dir)
    assert analyzer.execute() == 0
    content = analyzer.target_output_path.read_text(encoding="utf-8")
    assert "mod_a" in content
    assert "mod_b" in content


def test_main_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful CLI execution via main."""
    project_dir = tmp_path / "proj"
    src = project_dir / "src"
    src.mkdir(parents=True)
    (src / "main_mod.py").write_text("x = 1", encoding="utf-8")

    target_file_path = str(Path(fsd.__file__).resolve())
    monkeypatch.setattr(sys, "argv", ["workspace-stamper", str(project_dir)])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(target_file_path, run_name="__main__")
    assert exc_info.value.code == 0


def test_main_with_output_arg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful CLI execution with --output argument via main."""
    project_dir = tmp_path / "proj"
    src = project_dir / "src"
    src.mkdir(parents=True)
    (src / "main_mod.py").write_text("x = 1", encoding="utf-8")
    out_file = tmp_path / "output.md"

    target_file_path = str(Path(fsd.__file__).resolve())
    monkeypatch.setattr(
        sys,
        "argv",
        ["workspace-stamper", str(project_dir), "-o", str(out_file)],
    )

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(target_file_path, run_name="__main__")
    assert exc_info.value.code == 0
    assert out_file.exists()


def test_main_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI execution handling general exceptions in main."""
    target_file_path = str(Path(fsd.__file__).resolve())
    monkeypatch.setattr(sys, "argv", ["workspace-stamper", str(tmp_path)])

    def mock_init(
        self: CodeStructureAnalyzer,
        *args: object,
        **kwargs: object,
    ) -> Never:
        msg = "fatal init boom"
        raise RuntimeError(msg)

    monkeypatch.setattr(CodeStructureAnalyzer, "__init__", mock_init)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(target_file_path, run_name="__main__")
    assert exc_info.value.code == 1


def test_main_validation_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test CLI execution handling validation exceptions."""
    target_file_path = str(Path(fsd.__file__).resolve())
    invalid_path = tmp_path / "not_a_dir.txt"
    invalid_path.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["workspace-stamper", str(invalid_path)])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(target_file_path, run_name="__main__")
    assert exc_info.value.code == 1
