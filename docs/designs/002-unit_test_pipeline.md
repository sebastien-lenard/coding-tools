---
status: active  
date: 2026-10-19
---
<!-- docs/designs/unit_test_pipeline.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 0002: Automated Unit Test & Remediation Pipeline Design v0.1

This document details the multi-stage execution pipeline implemented by `batch-unit-test` and `unit_test_orchestrator`, including pre-pytest run checks, SPDX compliance auto-correction, runtime workspace guarding, tri-state outcomes, prioritized remediation gates, sidecar log artifacts, dynamic prompt construction, pytest edge cases, and deep runtime subtleties designed to guide AI agents and engineers effectively.

---

## Pipeline Architecture & Data Flow

When `batch-unit-test` runs against a target source file, it executes up to **5 iterations** per file. Each iteration follows a structured sequence of pre-pytest run checks, test execution, runtime workspace guard validation, and a strict 3-stage validation and AI remediation sequence:

```
[Start Iteration]
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ PRE-PYTEST RUN CHECKS & SPDX COMPLIANCE                         │
│ 1. Run `workspace_stamper` preemptively on test file        │
│    - Logs mutation status if headers added/corrected        │
│ 2. Static Validation Checks (Priority Ordered):             │
│    - (1) Code Length Check (> 5 lines)                      │
│    - (2) Syntax Validity Check (ast.parse)                  │
│    - (3) Static AST Check for `tmp_path` usage              │
│    - (4) SPDX Header Check                                  │
│ - Logs explicit synthesis line: [INFO] if all pass,         │
│   [WARNING] if any fail, with individual check statuses.    │
└──────┬──────────────────────────────────────────────────────┘
       │
       ├─► [PRE-PYTEST RUN FAILED / UNRESOLVED] ──► Query LLM Directly with Priority Fix Instructions
       │                                         (Bypasses pytest if static pre-checks fail;
       │                            writes fallback test log to prevent FileNotFoundError)
       │
       └─► [PRE-PYTEST RUN PASSED] ─────────────► Proceed to Stage 1: Pytest & Coverage
                                                 │
                                                 ▼
┌──────────────────────────────────────────────┐
│ STAGE 1: Pytest & Coverage Analysis          │
│ - Run pytest with --cov and term-missing     │
│ - Check for collection/syntax errors         │
│ - Run `workspace_guard` runtime check        │
│   (Detect unauthorized file pollution        │
│    outside `tmp_path`)                       │
│ - Extract warnings & log first line as       │
│   [WARNING] if present                       │
│ - Verify 100% test coverage & zero warnings  │
└──────┬───────────────────────────────────────┘
       │
       ├─► [PASSED] ──► Proceed to Stage 2
       │
       └─► [FAILED] ──► Query Gemini API with prioritized failures:
                          - (5) Pytest Errors / Exceptions
                          - (6) Runtime Unauthorized File Pollution
                          - (7) Test Assertions / Failures
                          - (8) Uncovered Code Blocks / Coverage
                          │
                          ▼
                        [Run LLM Response Validation Gates]
                          │
                          ├─► [INVALID] ──► Reject / Re-prompt LLM
                          │
                          └─► [VALID] ───► Persist AI fix to disk (Status: FIXED)
                                            │
                                            ▼
                                          [Next Iteration] (Re-test updated file)

       │ (If Stage 1 Passes)
       ▼
┌──────────────────────────────────────────────┐
│ STAGE 2: Basedpyright Type Checking          │
│ - Run basedpyright static analysis           │
└──────┬───────────────────────────────────────┘
       │
       ├─► [PASSED] ──► Proceed to Stage 3
       │
       └─► [FAILED] ──► Query Gemini API with type errors
                          │
                          ▼
                        [Run LLM Response Validation Gates]
                          │
                          ├─► [INVALID] ──► Reject / Re-prompt
                          │
                          └─► [VALID] ───► Persist AI fix to disk (Status: FIXED)
                                            │
                                            ▼
                                          [Next Iteration]
       │ (If Stage 2 Passes)
       ▼
┌──────────────────────────────────────────────┐
│ STAGE 3: Ruff Linting & Auto-Fix             │
│ - Run ruff check --fix                       │
└──────┬───────────────────────────────────────┘
       │
       ├─► [PASSED] ──► [Workflow SUCCESS: All Stages Passed]
       │
       └─► [FAILED] ──► Query Gemini API with lint errors
                          │
                          ▼
                        [Run LLM Response Validation Gates]
                          │
                          ├─► [INVALID] ──► Reject / Re-prompt
                          │
                          └─► [VALID] ───► Persist AI fix to disk (Status: FIXED)
                                            │
                                            ▼
                                          [Next Iteration]
```

---

## Detailed Gate Checks & Prioritized Remediation

1. **Tri-State Stage Outcomes (`WorkflowStatus`)**:
   - `SUCCESS`: The stage passed all local assertions cleanly without requiring intervention.
   - `FAILED`: The stage failed, and either LLM calls were disabled (`allow_gemini=False`) or the LLM hit a fatal stagnation / exception limit (`No solution`).
   - `FIXED`: Gemini successfully generated a valid, non-identical code fix passing all validation gates, which was persisted to disk. This triggers the iteration controller to feed the updated file into the next test cycle.

2. **Schema & Group Separation**:
   - **Schema Validation Group**: Validates response structure via Pydantic (`TestGenerationResponse`).
   - **Static Inspection Group**: Evaluates code length, `ast.parse` syntax, `tmp_path` static AST usage, and SPDX compliance.
   - **Runtime Workspace Guard Group (`workspace_guard.py`)**: Monitors file system state changes during test execution in Stage 1 to detect unauthorized file pollution outside approved temporary directories.

3. **Pre-Pytest Run Execution Gating**:
   - `workspace_stamper` runs automatically before any test execution to guarantee header compliance.
   - If static pre-checks (1–4) fail and cannot be auto-corrected, pytest is **not** run; control delegates directly to the LLM remediation loop with precise error instructions, while ensuring a fallback test log is written to disk.

4. **Progression & Iteration Boundaries**:
   - If a fix is applied during any stage, the orchestrator returns control so the next iteration validates the new test code from scratch.
   - On the **last allowed iteration** (`max_iterations`), Gemini authorization is disabled (`allow_gemini = False`), serving as a strict read-only audit run to prevent infinite LLM loops.

5. **Prioritized Failure Remediation Order**:
   - When issues are passed to the LLM, priorities are strictly ordered:
     1. Code Length (ensure complete script is returned)
     2. Syntax (`ast.parse`)
     3. `tmp_path` isolation (static AST)
     4. SPDX Header Compliance
     5. Pytest Execution / Assertion Errors
     6. Runtime Unauthorized File Pollution
     7. Failed Tests
     8. Test Coverage / Uncovered Blocks

---

## Sidecar Log Artifacts & File System Interfacing

The pipeline generates persistent sidecar log artifacts and coverage reports during test executions. To prevent repository clutter and keep production source folders clean, all artifacts are routed into dedicated isolated directories managed by `file_handler.py`:

- **Pytest Logs (`.pytest_output/unit-test-{test_stem}.txt`)**: Captured by `WorkspaceGuard` and parsers during test execution, containing the exact command invocation, stdout, stderr, and failure tracebacks.
- **Pyright Logs (`.pyright_output/based-pyright-{test_stem}.txt`)**: Captured during Basedpyright static type-checking passes.
- **Ruff Logs (`.ruff_output/ruff-{test_stem}.txt`)**: Captured during Ruff linting and auto-fix passes.
- **Coverage Annotations (`.coverage_annotations/{source_filename},cover`)**: Generated by `pytest-cov` (`--cov-report=annotate:.coverage_annotations`), marking uncovered source lines with `!` or `>`. These are inspected programmatically by `extract_uncovered_blocks` and `generate_coverage_hints`.

---

## Dynamic Prompt Construction & Pytest Parsing Edge Cases

1. **Dynamic Prompt Assembly (`build_contents_list`)**:
   - Prompts sent to the LLM are assembled dynamically. Depending on whether remote caching is active, context files (`pyproject.toml`, `conftest.py`, source code) are either cached via Gemini context caching or appended explicitly as agnostic text blocks.
   - Crucially, parsers extract specific subsets of failure metadata—such as `E ` assertion lines (`extract_pytest_errors`), warnings summaries (`extract_pytest_warnings`), uncovered blocks (`extract_uncovered_blocks`), and programmatic branch/compound boolean hints (`generate_coverage_hints`)—and insert them into structured priority sections.

2. **Pytest Output Parsing & Collection Error Edge Cases**:
   - Pytest output parsing handles two distinct categories of failure:
     - **Collection / Syntax Errors (`_check_pytest_syntax_error`)**: Triggered when syntax errors or collection failures occur (e.g., `SyntaxError` or `Interrupted: 1 error during collection`). In these cases, execution bypasses standard test evaluation and routes the raw traceback directly to the LLM via a dedicated custom content payload (`_build_pytest_custom_contents`) instructing it to fix the fatal syntax issue.
     - **Assertion & Coverage Evaluation**: Parses the summary line and term-missing coverage tables, matching target source paths (handling both POSIX and Windows slashes) to accurately compute missing lines and verify 100% test coverage.

---

## Critical Runtime Subtleties & LLM Blind Spots

When working with or generating test scripts for this codebase, an LLM or developer might struggle with several non-obvious runtime constraints unless explicitly aware of them:

1. **Workspace Guard Extension Scope**:
   - `WorkspaceGuard` exclusively tracks and monitors newly created **`.py` files** for runtime workspace pollution (`CHECKED_EXTENSIONS = {".py"}`). Non-Python sidecar files (like `.txt`, `.log`, or `.cover` files) are intentionally ignored by the guard engine, leaving them intact for debugging.
2. **Static AST Isolation Fixture Recognition**:
   - To pass `WorkspaceGuard` static isolation checks without triggering violations, any test function performing file I/O or directory creation must declare either `tmp_path` or `setup_mock_project` in its parameter signature.
3. **Dynamic Prompt Filtering**:
   - The orchestrator dynamically filters out passing checks from LLM remediation prompts. If pre-pytest static checks (Length, Syntax, Isolation, SPDX) pass, they are completely omitted from the prompt payload so the LLM remains focused solely on active failures (e.g., test assertions or coverage gaps).
4. **Identical Code Guardrails & Stagnation Detection**:
   - If the LLM repeatedly returns code identical to the existing test file, the remediator intercepts it (`identical_attempts >= 1`), logs a warning with the prioritized remediation plan, and aborts with `"No solution"` if stagnation persists, preventing infinite API loops.