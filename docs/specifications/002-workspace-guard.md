---
status: active  
date: 2026-10-21
---
<!-- docs/designs/workspace_guard_implementation_plan.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Implementation Plan: Guarded Unit Test & Remediation Pipeline (Revised)

This implementation plan incorporates all refined requirements, CLI entrypoints, workspace-guard execution semantics, exclusion filtering, logging adjustments (treating runtime workspace pollution as non-blocking warnings so scans continue across all files), executive summary tables, and programmatic LLM remediation payload integration.

---

## Phase 1: Build & Refine the Robust Workspace Guard Module (`src/coding_tools/workspace_guard.py`)
1. **Static AST Analysis**:
   - Traverse test script AST to inspect test function signatures and bodies.
   - Detect test functions performing file/output operations that lack proper sandboxing or reference root workspace paths improperly.
   - Properly ignore virtual environments (`.venv`, `venv`, etc.) and non-test files during project-wide scans.
2. **Runtime Workspace Snapshot & Diff (Executing Test Runner)**:
   - Capture a pre-execution baseline snapshot of the workspace repository.
   - Execute the target test file(s) via `pytest` programmatically or via subprocess.
   - Capture a post-execution snapshot and diff against baseline.
   - Detect and report unauthorized untracked file pollution as **[WARNING]** alerts (allowing the guard process to continue scanning remaining test files rather than aborting prematurely).
3. **CLI, Standalone Entrypoint & Executive Summary Table**:
   - Provide clear, mutually exclusive CLI options (`--static`, `--runtime`, `--all`).
   - Log every phase of execution with explicit INFO/WARNING messages.
   - Print a clean executive summary table at the end of execution showing total files processed, static/runtime pass/fail counts, and specific violation details.
4. **Project Script Registration**:
   - Register `workspace-guard = "coding_tools.workspace_guard:main"` in `pyproject.toml`.

---

## Phase 2: Update Parsers and Pre-Flight Validators (`src/coding_tools/parsers.py`)
1. **Pre-Flight Checks & SPDX Auto-Correction**:
   - Implement pre-flight validation functions incorporating `workspace_stamper` to preemptively check and auto-correct SPDX headers on test files before execution, logging mutation results.
   - Implement static validation checks for code length (> 5 lines), syntax (`ast.parse`), and static `tmp_path` isolation (leveraging `WorkspaceGuard`).

2. **Prioritized Validation Order & Error Formatting**:
   - Strictly order errors according to the 8-point priority hierarchy:
     1. Code Length
     2. Syntax (`ast.parse`)
     3. `tmp_path` isolation (static AST)
     4. SPDX Header Compliance
     5. Pytest Execution / Assertion Errors
     6. Runtime Unauthorized File Pollution
     7. Failed Tests
     8. Test Coverage / Uncovered Blocks
   - Format and expose these prioritized errors so they can be injected cleanly into LLM remediation payloads.

3. **Execution Trace Logging**:
   - Ensure every validation step, auto-correction, and failure check emits detailed INFO/WARNING/ERROR logs.

---

## Phase 3: Refactor Remediator & Orchestrator (`src/coding_tools/llm_remediation.py` & `unit_test_orchestrator.py`)
1. **Pre-Flight Execution Gating**:
   - Execute pre-flight static checks and `workspace_stamper` before running pytest.
   - If static pre-checks fail and cannot be resolved, bypass pytest entirely and route the failure directly to LLM remediation with high-priority instructions based on the priority order.
2. **Runtime Guard Integration & Payload Injection**:
   - Programmatically invoke `workspace_guard` during Stage 1 test execution to catch runtime file pollution.
   - Feed static and runtime guard violations directly into the LLM prompt payload under the strict 8-point priority hierarchy.

---

## Phase 4: Comprehensive Unit & Integration Testing (`tests/unit/test_workspace_guard.py`, etc.)
1. **Test Workspace Guard**:
   - Write unit tests verifying static AST detection of missing `tmp_path`.
   - Write unit tests verifying runtime snapshot diffing catches unauthorized file creation and ignores approved temp dirs and test tool output logs.
2. **Test Pipeline Gating**:
   - Test pre-flight bypass when static checks fail.
   - Test preemptive SPDX auto-correction via `workspace_stamper`.