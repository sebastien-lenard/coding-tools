---
status: active  
date: 2026-10-20
---
<!-- docs/specifications/001-function-signatures-dependencies-v0.1.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Implementation Plan: Python Source Code Structure & Dependency Analyzer (`function_signatures_dependencies`)

## 1. Objective
Build a command-line tool (`function_signatures_dependencies.py`) that statically analyzes a Python project's `src` folder using the built-in `ast` module. The tool extracts structural metadata (modules, global constants, classes, inheritance, decorators, function signatures, uncaught exceptions, and function-level call graphs) and compiles everything into a single, highly structured Markdown document optimized for LLM comprehension. It appends the project's `pyproject.toml` at the end.

---

## 2. Technical Stack & Constraints
* **Language**: Python 3.12.9
* **Libraries**: Standard library only for parsing (`ast`, `pathlib`, `argparse`, `logging`, `sys`), plus `pydantic` for configuration validation.
* **Typing**: Strict type annotations compatible with `basedpyright`.
* **Linting**: Must adhere to `ruff` rules configured in the project (no boolean parameters/arguments, strict docstrings where applicable).

---

## 3. Detailed Component Specifications

### A. Configuration & CLI (`SourceStructureAnalyzer` Pydantic Model)
* **Inputs**:
  * `project_path` (DirectoryPath): Root folder of the project being analyzed (default: current working directory `.`).
  * `output_file` (Path | None): Destination markdown file path. If `None`, dynamically resolved to `{project_name}_structure.md` at the root of `project_path`, where `{project_name}` is derived from the folder name or `pyproject.toml`.
* **Execution Flow**:
  1. Validate that `project_path / "src"` exists and is a directory.
  2. Locate and validate access to `pyproject.toml` at the project root.
  3. Execute the AST extraction engine across all `.py` files inside `src/` (ignoring `__pycache__`, `.git`, `venv`, etc.).
  4. Write the final formatted Markdown output.

### B. AST Extraction Engine (Per Module)
For each `.py` file found in `src/`, the parser extracts the following structures into intermediate data classes or dictionaries:
1. **Module Metadata**:
   * Relative path from `src/`.
   * Module docstring.
2. **Global Constants / Variables**:
   * Top-level assignments (`ast.Assign` or `ast.AnnAssign` directly under the module body, outside any class or function). Example: `HTTP_SERVICE_UNAVAILABLE = 503`.
3. **Imports & Conditional Imports**:
   * All import statements (`ast.Import` and `ast.ImportFrom`), including those nested inside `if` statements or `try/except` blocks.
4. **Classes**:
   * Name, docstring, and decorators.
   * Inheritance bases (extracted from `class ClassName(BaseClass):`).
   * Methods (name, decorators, signature parameters, return annotations, uncaught exceptions, callers/callees).
5. **Standalone Functions**:
   * Exclude functions defined *inside* other functions (only inspect top-level functions within the module).
   * Name, docstring, and decorators.
   * Signature parameters and return type annotations.
   * **Uncaught Exceptions**: Identify `ast.Raise` nodes that do not occur within the body of a local `try/except` handler inside that function/method.
   * **Function-Level Dependencies (Call Graph)**: Extract all `ast.Call` nodes within the function body to map local callees.

### C. Cross-Reference & Graph Resolution
1. **Module Dependencies**: Build a directed graph of internal imports between modules inside `src/` to feed into a Mermaid.js diagram.
2. **Function Call Graph**: Aggregate function and method definitions across all parsed modules to resolve local callers and callees. If a call matches a known function name within the project scope, link it; otherwise, label it as an external or unresolved call.

---

## 4. Markdown Output Structure

The generated markdown document (`[project_name]_structure.md`) will contain:

1. **Title & Overview**: Metadata about the analyzed project.
2. **Project Tree**: ASCII tree representation of the `src` directory.
3. **Module Dependency Graph**: A Mermaid.js flowchart (`graph TD`) illustrating internal module-to-module imports.
4. **Module Breakdown**: For each module:
   * **Module Docstring**
   * **Global Constants**
   * **Classes**:
     * Inheritance & Decorators
     * Methods (Signatures, Decorators, Uncaught Exceptions, Calls / Called By)
   * **Functions**:
     * Signatures, Decorators, Uncaught Exceptions, Calls / Called By
5. **Appendix**: Raw text content of `pyproject.toml`.

---

## 5. Potential Edge Cases & Solutions (Addressing LLM/Parser Ambiguities)
* **Ambiguity**: *What happens if a function calls a method of an instantiated object (e.g., `self.helper.validate()`)?*
  * **Solution**: The parser extracts the call name (`validate` or attribute call chain) and records it in the callee list so the LLM is aware of the interaction.
* **Ambiguity**: *How do we definitively distinguish global constants from local temporary variables?*
  * **Solution**: Only capture assignment nodes whose direct parent is the `ast.Module` node (ignoring assignments inside `FunctionDef`, `AsyncFunctionDef`, or `ClassDef`).
* **Ambiguity**: *How do we know if an exception is truly "uncaught"?*
  * **Solution**: Walk the subtree of the function/method. If an `ast.Raise` node is encountered, check its ancestor path within that function for an `ast.Try` node. If none exists, flag it as an uncaught exception signature.
