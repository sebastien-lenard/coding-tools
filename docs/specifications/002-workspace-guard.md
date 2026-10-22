---
status: active  
date: 2026-10-21
---
<!-- docs/designs/workspace_guard_implementation_plan.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Implementation Plan: Guarded Unit Test & Remediation Pipeline

This implementation plan incorporates all refined requirements, explicit non-ambiguous logging rules (single-line synthesis for pre-pytest run checks with `[INFO]` on pass and `[WARNING]` on fail, and explicit first-line warning snippet logging), CLI entrypoints, workspace-guard execution semantics, exclusion filtering, logging adjustments (treating runtime workspace pollution as non-blocking warnings so scans continue across all files), executive summary tables, and programmatic LLM remediation payload integration.

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
   - we only only track and monitor files matching allowed/checked extensions, defined in an array constant at the top of workspace_guard.py: CHECKED_EXTENSIONS = {".py"}
   - the pytest command should generate unit test coverage files (see rules to detect source script below)
   - the pytest command stdout/stderr should be saved in a unit-test-{test_stem}.txt file (that can be read by other tools)
3. **WorkspaceGuard Status Semantics**: Decouple test assertion failures from workspace pollution guard results:
   - **PASSED**: Test execution succeeded cleanly with zero workspace pollution.
   - **WARNING**: Test execution failed (assertion error, test failure, or standard pytest error) but zero workspace pollution occurred. The process continues to LLM remediation.
   - **FAILED**: Workspace pollution guard detected unauthorized file creation/pollution (or a critical guard inspection failure occurred).
NB: We treat runtime test assertion failures or non-zero pytest return codes (excluding fatal guard execution exceptions) as `WARNING` in terms of summary classification while still triggering remediation. If `WorkspaceGuard` experiences a system-level or unexpected exception during execution, it logs an error and returns failure.

3. **CLI, Standalone Entrypoint & Executive Summary Table**:
   - Provide clear, mutually exclusive CLI options (`--static`, `--runtime`, `--all`).
   - Log every phase of execution with explicit INFO/WARNING messages.
   - Print a clean executive summary table at the end of execution showing total files processed, static/runtime pass/fail counts, and specific violation details.
4. **Project Script Registration**:
   - Register `workspace-guard = "coding_tools.workspace_guard:main"` in `pyproject.toml`.

---

## Phase 2: Update Parsers and Pre-Pytest Run Validators (`src/coding_tools/parsers.py`)
1. **Pre-Pytest Run Checks & SPDX Auto-Correction**:
   - Implement pre-pytest run validation functions incorporating `workspace_stamper` to preemptively check and auto-correct SPDX headers on test files before execution, logging mutation results.
   - Execute static checks (1: Code Length, 2: Syntax, 3: `tmp_path` isolation, 4: SPDX Header) and log results in a single structured synthesis line: `[INFO]` if all pass, `[WARNING]` if any fail, detailing each check's status.
   - When pre-pytest run static checks fail, bypass pytest but ensure a dummy or descriptive `unit-test-{test_stem}.txt` log file is written to disk. This prevents `read_local_files` from throwing a `FileNotFoundError` when attempting to collect payloads for LLM remediation.
   - Implement static validation checks for code length (> 5 lines), syntax (`ast.parse`), and static `tmp_path` isolation (leveraging `WorkspaceGuard`).
   - Parsers should parse the missing line numbers from the coverage report.

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
1. **Pre-Pytest Run Execution Gating**:
   - Execute pre-pytest run static checks and `workspace_stamper` before running pytest (using `run_preflight_compliance_and_validation`).
   - If pre-pytest run static checks fail, bypass pytest entirely, log the exact prioritized errors, and route control directly to LLM remediation with high-priority instructions.
   - When pytest completes, if warnings are extracted, log the first line of the warning snippet explicitly with a `[WARNING]` label so execution is never in the dark.
2. **Runtime Guard Integration**:
   - Invoke `WorkspaceGuard` during Pytest/Coverage execution to capture baseline snapshots, run tests, and detect unauthorized runtime workspace file pollution.
   - Inject runtime pollution errors (Priority 6) alongside Pytest errors (Priority 5), test failures (Priority 7), and coverage issues (Priority 8) into the LLM payload.
3. **Execution Trace Logging**:
   - Ensure every decision point (pre-pytest run pass/fail, pytest run, runtime guard status, LLM remediation request/response) emits clear INFO/WARNING/ERROR trace logs.

---

## Phase 4: Comprehensive Unit & Integration Testing (`tests/unit/test_workspace_guard.py`, etc.)
1. **Test Workspace Guard**:
   - Write unit tests verifying static AST detection of missing `tmp_path`.
   - Write unit tests verifying runtime snapshot diffing catches unauthorized file creation and ignores approved temp dirs and test tool output logs.
2. **Test Pipeline Gating**:
   - Test pre-pytest run bypass when static checks fail.
   - Test preemptive SPDX auto-correction via `workspace_stamper`.

---

## Phase 5: Complementary update to the plan to clarify logging

This complementary plan adddresses additional logging, diagnostics, and LLM visibility requirements.

#### 1: Contextual Logging Consistency (Addressing Issue #1)
- **Objective**: Ensure all workflow steps, compliance checks, and guard executions consistently prepend `[<test_filename>]`.
- **Approach**: 
  - Pass the execution `prefix` (e.g., `test_backup_untracked.py`) into utility modules or wrap loggers with a contextual adapter in `WorkspaceStamper`, `WorkspaceGuard`, and parser helpers where appropriate, ensuring log lines cleanly identify which test file is being processed.

#### 2: Granular Post-Pytest Evaluation Logs (Addressing Issue #2)
- **Objective**: Make post-pytest check evaluations transparent.
- **Approach**: 
  - Refactor `_evaluate_pytest_success` in `llm_remediation.py` to output explicit, distinct log entries for each evaluation vector:
    1. Pytest Errors / Tracebacks
    2. Test Isolation / `tmp_path` Compliance
    3. Pytest Warnings
    4. Test Assertions / Failures
    5. Code Coverage Status & Missing Lines

### 3: Detailed Workspace Pollution Diagnostics (Addressing Issue #3)
- **Objective**: Exclude ambiguity around runtime pollution.
- **Approach**: 
  - Update `check_runtime_pollution` in `workspace_guard.py` so that the warning log directly outputs the unauthorized file paths (e.g., `Runtime workspace pollution detected (1 unauthorized files: ['unauthorized_file.txt'])`).

#### 4: Transparent LLM Prompt & Prioritization Payload Logging (Addressing Issue #5)
- **Objective**: Diagnose why an LLM returns identical code (whether due to prompt artifacts or internal LLM looping).
- **Approach**: 
  - When the LLM returns identical code and triggers a retry, log an `INFO`-level message displaying the structured list of prioritization points sent to the LLM in that request (e.g., the ordered list of errors, missing coverage blocks, workspace pollution violations, and explicit remediation constraints). This will let you instantly see if the tool's instructions are clear or if the LLM is ignoring them due to complex decorator/fixture interactions.

---

## Phase 6: Complementary update to dynamically prompt the llm and improve logging

1. **Contextual & Terminology Refinement**:
   - Standardize log prefixing with `[<test_filename>]` across batch execution loops, compliance engines, and guard checks.
   - Rename "pre-pytest run" to **"pre-pytest run"** and output clean, structured **"post-pytest run"** synthesis status logs (avoiding True/False verbosity).
2. **WorkspaceGuard Coverage Support**:
   - Add the `run_coverage: bool` parameter (defaulting to `False`) to `execute_test_and_guard` in `workspace_guard.py`.
   - Automatically derive the corresponding source module path from the test filename when `run_coverage=True` so `.cover` report files are generated.
   - OS-agnostic module path conversion to ensure that whether `source_file_path` is passed explicitly or derived, pytest coverage correctly targets module paths like `thispackage.toto` or `thispackage.subfolder.toto` by resolving relative to `src` (e.g. for tests\unit\subfolder\test_toto.py, the script to be covered is src\thispackage\subfolder\toto.py)
   - Coverage Parsing Fix: Ensure `_extract_coverage_metrics` robustly matches the coverage table lines using both relative source paths and normalized module names so 100% coverage is correctly detected and never reports `None` incorrectly.
3. **Dynamic LLM Remediation Prompts**:
   - Filter out passing checks and avoid injecting boilerplate warnings into LLM payloads.
   - Formulate clean, direct prompts focused exclusively on active failures (pollution, assertion failures, or missing coverage).
