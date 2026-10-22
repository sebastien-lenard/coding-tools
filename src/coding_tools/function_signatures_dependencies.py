# src/coding_tools/function_signatures_dependencies.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Extracts functions, classes, signatures, exceptions, and dependencies.

from a project's src folder into a structured LLM-ready markdown document.
"""

import argparse
import ast
import logging
import os
import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, DirectoryPath

# Force Python into UTF-8 mode on Windows
os.environ["PYTHONUTF8"] = "1"

logger = logging.getLogger("coding_tools.function_signatures_dependencies")


class FunctionInfo(BaseModel):
    """Metadata for a function or method."""

    name: str
    signature: str
    docstring: str | None
    decorators: list[str]
    uncaught_exceptions: list[str]
    calls: list[str]
    called_by: list[str] = []


class ClassInfo(BaseModel):
    """Metadata for a class."""

    name: str
    docstring: str | None
    bases: list[str]
    decorators: list[str]
    methods: list[FunctionInfo]


class ModuleInfo(BaseModel):
    """Metadata for a parsed source module."""

    path: Path
    relative_path: str
    docstring: str | None
    constants: dict[str, str]
    imports: list[str]
    classes: list[ClassInfo]
    functions: list[FunctionInfo]


class CodeStructureAnalyzer(BaseModel):
    """Performs static AST analysis and generates an LLM-ready markdown summary."""

    project_path: DirectoryPath
    output_file: Path | None = None

    _ignore_dirs: ClassVar[set[str]] = {"__pycache__", ".git", "venv", ".venv"}

    @property
    def target_output_path(self) -> Path:
        """Returns the calculated output file path."""
        if self.output_file:
            return self.output_file
        project_name = self.project_path.resolve().name
        return self.project_path / f"{project_name}_structure.md"

    @property
    def src_path(self) -> Path:
        """Returns the expected 'src' subfolder path."""
        return self.project_path / "src"

    def execute(self) -> int:
        """Orchestrates code analysis and markdown generation.

        Returns status code integer.
        """
        logger.info(
            "Starting CodeStructureAnalyzer workflow execution for project path: [%s]",
            self.project_path,
        )

        if not self.src_path.exists() or not self.src_path.is_dir():
            logger.error(
                "[src path missing] Required 'src' subfolder missing at target: [%s]",
                self.src_path,
            )
            return 1

        modules = self._analyze_modules()
        if not modules:
            logger.warning(
                "[no modules found] No python modules found in [%s]",
                self.src_path,
            )
            return 1

        self._resolve_call_graphs(modules)
        logger.info(
            "Successfully resolved call graphs across analyzed modules.",
        )

        markdown_content = self._generate_markdown(modules)

        output_path = self.target_output_path
        try:
            output_path.write_text(markdown_content, encoding="utf-8")
        except OSError:
            logger.exception(
                "[file write error] Failed to write structure markdown to: [%s]",
                output_path,
            )
            return 1

        logger.info(
            "Successfully generated markdown output at: [%s]",
            output_path,
        )
        logger.info(
            "Workflow execution summary: Status=SUCCESS, ModulesAnalyzed=%d,"
            " TargetOutput=%s",
            len(modules),
            output_path.name,
        )
        return 0

    def _analyze_modules(self) -> list[ModuleInfo]:
        """Scan and parse all .py files in the src folder."""
        modules: list[ModuleInfo] = []
        source_files = [
            path
            for path in self.src_path.rglob("*.py")
            if not any(part in self._ignore_dirs for part in path.parts)
            and path.is_file()
        ]

        source_files.sort()

        for file_path in source_files:
            rel_path = file_path.relative_to(self.src_path).as_posix()
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"))
            except Exception:
                logger.exception(
                    "[ast parse error] Failed to parse AST for file: [%s]",
                    file_path,
                )
                continue

            module_info = self._parse_ast_tree(tree, file_path, rel_path)
            modules.append(module_info)

        logger.info(
            "Successfully parsed [%03d] python modules from src folder.",
            len(modules),
        )
        return modules

    def _parse_ast_tree(
        self,
        tree: ast.Module,
        file_path: Path,
        rel_path: str,
    ) -> ModuleInfo:
        """Extract module-level elements from an AST tree."""
        docstring = ast.get_docstring(tree)
        constants: dict[str, str] = {}
        imports: list[str] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []

        for node in tree.body:
            self._process_node(
                node,
                constants,
                imports,
                classes,
                functions,
            )

        return ModuleInfo(
            path=file_path,
            relative_path=rel_path,
            docstring=docstring,
            constants=constants,
            imports=imports,
            classes=classes,
            functions=functions,
        )

    def _process_node(
        self,
        node: ast.stmt,
        constants: dict[str, str],
        imports: list[str],
        classes: list[ClassInfo],
        functions: list[FunctionInfo],
    ) -> None:
        """Process individual AST statement nodes at the module level."""
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            self._process_import_from(node, imports)
        elif isinstance(node, ast.Assign):
            self._process_assign(node, constants)
        elif isinstance(node, ast.AnnAssign):
            self._process_ann_assign(node, constants)
        elif isinstance(node, ast.ClassDef):
            classes.append(self._parse_class_node(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(self._parse_function_node(node))

    def _process_import_from(
        self,
        node: ast.ImportFrom,
        imports: list[str],
    ) -> None:
        """Process ImportFrom AST nodes."""
        mod_name = node.module or ""
        for alias in node.names:
            full_imp = f"{mod_name}.{alias.name}" if mod_name else alias.name
            imports.append(full_imp)

    def _process_assign(
        self,
        node: ast.Assign,
        constants: dict[str, str],
    ) -> None:
        """Process Assign AST nodes for global constants."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                try:
                    constants[target.id] = ast.unparse(node.value)
                except OSError:
                    constants[target.id] = "<complex>"

    def _process_ann_assign(
        self,
        node: ast.AnnAssign,
        constants: dict[str, str],
    ) -> None:
        """Process AnnAssign AST nodes for global constants."""
        if isinstance(node.target, ast.Name):
            try:
                val_str = ast.unparse(node.value) if node.value else "<unassigned>"
                constants[node.target.id] = val_str
            except OSError:
                constants[node.target.id] = "<complex>"

    def _parse_class_node(self, node: ast.ClassDef) -> ClassInfo:
        """Extract class definition metadata."""
        docstring = ast.get_docstring(node)
        bases = [self._safe_unparse(base) for base in node.bases]
        decorators = [self._safe_unparse(dec) for dec in node.decorator_list]
        methods = [
            self._parse_function_node(subnode)
            for subnode in node.body
            if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        return ClassInfo(
            name=node.name,
            docstring=docstring,
            bases=bases,
            decorators=decorators,
            methods=methods,
        )

    def _parse_function_node(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> FunctionInfo:
        """Extract function or method signature and internal metrics."""
        docstring = ast.get_docstring(node)
        decorators = [self._safe_unparse(dec) for dec in node.decorator_list]
        signature = self._build_signature(node)
        uncaught_exceptions = self._find_uncaught_exceptions(node)
        calls = self._find_calls(node)

        return FunctionInfo(
            name=node.name,
            signature=signature,
            docstring=docstring,
            decorators=decorators,
            uncaught_exceptions=uncaught_exceptions,
            calls=calls,
        )

    def _safe_unparse(self, node: ast.AST) -> str:
        """Safely unparse an AST node to string."""
        try:
            return ast.unparse(node)
        except OSError:
            return "<expr>"

    def _build_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        """Reconstruct a readable signature for a function/method."""
        args_str = self._safe_unparse(node.args)
        returns_str = f" -> {self._safe_unparse(node.returns)}" if node.returns else ""
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({args_str}){returns_str}"

    def _find_uncaught_exceptions(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        """Detect raise statements not enclosed in a local try/except block."""
        uncaught: list[str] = []

        class ExceptionVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.try_depth = 0

            def visit_Try(self, node: ast.Try) -> None:
                self.try_depth += 1
                self.generic_visit(node)
                self.try_depth -= 1

            def visit_Raise(self, node: ast.Raise) -> None:
                if self.try_depth == 0 and node.exc:
                    exc_str = ast.unparse(node.exc)
                    if exc_str not in uncaught:
                        uncaught.append(exc_str)
                self.generic_visit(node)

        visitor = ExceptionVisitor()
        for stmt in node.body:
            visitor.visit(stmt)

        return uncaught

    def _find_calls(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        """Extract function/method calls made inside a function scope."""
        calls: list[str] = []

        class CallVisitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                call_str = ast.unparse(node.func)
                if call_str not in calls:
                    calls.append(call_str)
                self.generic_visit(node)

        visitor = CallVisitor()
        for stmt in node.body:
            visitor.visit(stmt)

        return calls

    def _resolve_call_graphs(self, modules: list[ModuleInfo]) -> None:
        """Cross-reference function calls to build 'called_by' relationships."""
        function_registry: dict[str, list[FunctionInfo]] = {}

        for module in modules:
            for func in module.functions:
                function_registry.setdefault(func.name, []).append(func)
            for cls in module.classes:
                for method in cls.methods:
                    function_registry.setdefault(
                        method.name,
                        [],
                    ).append(method)

        for module in modules:
            for func in module.functions:
                self._link_callers(func.calls, func.name, function_registry)
            for cls in module.classes:
                for method in cls.methods:
                    self._link_callers(
                        method.calls,
                        method.name,
                        function_registry,
                    )

    def _link_callers(
        self,
        calls: list[str],
        caller_name: str,
        registry: dict[str, list[FunctionInfo]],
    ) -> None:
        """Link caller to target functions in registry."""
        for callee_name in calls:
            short_name = callee_name.split(".")[-1]
            if short_name in registry:
                for target_func in registry[short_name]:
                    if caller_name not in target_func.called_by:
                        target_func.called_by.append(caller_name)

    def _append_docstring(
        self,
        docstring: str | None,
        lines: list[str],
        indent: str = "",
    ) -> None:
        """Append rendered docstring block."""
        if docstring:
            for doc_line in docstring.strip().splitlines():
                if doc_line.strip():
                    lines.append(f"{indent}> {doc_line.strip()}")
                else:
                    lines.append(f"{indent}>")
            lines.append("")

    def _append_module_header(
        self,
        mod: ModuleInfo,
        lines: list[str],
    ) -> None:
        """Append module header and docstring to lines."""
        lines.append(f"### Module: `{mod.relative_path}`")
        lines.append("")
        self._append_docstring(mod.docstring, lines, indent="")

    def _append_module_constants(
        self,
        mod: ModuleInfo,
        lines: list[str],
    ) -> None:
        """Append global constants to lines."""
        if mod.constants:
            lines.append("#### Global Constants")
            for c_name, c_val in mod.constants.items():
                lines.append(f"- `{c_name} = {c_val}`")
            lines.append("")

    def _append_function_details(
        self,
        func: FunctionInfo,
        lines: list[str],
        indent: str = "",
    ) -> None:
        """Append function/method details to lines."""
        prefix = f"{indent}- "
        lines.append(f"{prefix}`{func.signature}`")
        lines.append("")
        if func.docstring:
            self._append_docstring(func.docstring, lines, indent=f"{indent}  ")
        sub_indent = f"{indent}  - "
        if func.decorators:
            lines.append(
                f"{sub_indent}*Decorators*: {', '.join(func.decorators)}",
            )
        if func.uncaught_exceptions:
            exc_list = ", ".join(func.uncaught_exceptions)
            lines.append(f"{sub_indent}*Uncaught Exceptions*: `{exc_list}`")
        if func.calls:
            calls_list = ", ".join(func.calls)
            lines.append(f"{sub_indent}*Calls*: `{calls_list}`")
        if func.called_by:
            called_by_list = ", ".join(func.called_by)
            lines.append(f"{sub_indent}*Called By*: `{called_by_list}`")

    def _append_module_classes(
        self,
        mod: ModuleInfo,
        lines: list[str],
    ) -> None:
        """Append classes and methods to lines."""
        if mod.classes:
            lines.append("#### Classes")
            for cls in mod.classes:
                bases_str = f"({', '.join(cls.bases)})" if cls.bases else ""
                decorators_str = (
                    " ".join(cls.decorators) + " " if cls.decorators else ""
                )
                lines.append(
                    f"- **`{decorators_str}class {cls.name}{bases_str}`**",
                )
                lines.append("")
                if cls.docstring:
                    self._append_docstring(cls.docstring, lines, indent="    ")
                for method in cls.methods:
                    self._append_function_details(method, lines, indent="  ")
            lines.append("")

    def _append_module_functions(
        self,
        mod: ModuleInfo,
        lines: list[str],
    ) -> None:
        """Separator for standalone functions."""
        if mod.functions:
            lines.append("#### Functions")
            for func in mod.functions:
                self._append_function_details(func, lines, indent="")
            lines.append("")

    def _append_dependency_graph(
        self,
        modules: list[ModuleInfo],
        lines: list[str],
    ) -> None:
        """Append Mermaid.js module dependency graph."""
        lines.append("## 📊 Module Dependency Graph")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph TD")
        for mod in modules:
            mod_node = mod.relative_path.replace("/", "_").replace(".py", "")
            for imp in mod.imports:
                for target_mod in modules:
                    target_rel = target_mod.relative_path.replace("/", ".").replace(
                        ".py",
                        "",
                    )
                    if imp.startswith(target_rel):
                        imp_node = imp.replace(".", "_")
                        lines.append(f"    {mod_node} --> {imp_node}")
        lines.append("```")
        lines.append("")

    def _generate_markdown(self, modules: list[ModuleInfo]) -> str:
        """Compile all analyzed data into an LLM-ready markdown string."""
        lines: list[str] = []

        project_name = self.project_path.resolve().name
        lines.append(f"# Project Architecture Map: {project_name}")
        lines.append("")
        lines.append(
            "This document contains structural signatures, "
            "type annotations, exceptions, and dependency graphs "
            "extracted via static AST analysis.",
        )
        lines.append("")

        lines.append("## 📁 Source Tree")
        lines.append("")
        lines.extend(f"- `{mod.relative_path}`" for mod in modules)
        lines.append("")

        self._append_dependency_graph(modules, lines)

        lines.append("## 📦 Modules Breakdown")
        lines.append("")

        for mod in modules:
            self._append_module_header(mod, lines)
            self._append_module_constants(mod, lines)
            self._append_module_classes(mod, lines)
            self._append_module_functions(mod, lines)
            lines.append("---")
            lines.append("")

        pyproject_path = self.project_path / "pyproject.toml"
        if pyproject_path.exists() and pyproject_path.is_file():
            lines.append("## ⚙️ pyproject.toml")
            lines.append("")
            lines.append("```toml")
            lines.append(pyproject_path.read_text(encoding="utf-8"))
            lines.append("```")
            lines.append("")

        return "\n".join(lines)


def main() -> None:
    """CLI Gateway transforming raw arguments into verified analysis contexts."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract functions, classes, signatures, and dependencies "
            "from a project's src folder into an LLM-ready markdown document."
        ),
    )
    parser.add_argument(
        "project_path",
        type=str,
        nargs="?",
        default=".",
        help=("Path to the target project directory (default: current directory)"),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help=(
            "Destination markdown file path "
            "(default: '[project_name]_structure.md' at project root)"
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        analyzer = CodeStructureAnalyzer(
            project_path=Path(args.project_path),
            output_file=Path(args.output) if args.output else None,
        )
        status_code = analyzer.execute()
    except Exception:
        logger.exception(
            "[fatal error] Execution terminated due to validation breakdown",
        )
        status_code = 1

    sys.exit(status_code)


if __name__ == "__main__":  # pragma: no cover
    main()
