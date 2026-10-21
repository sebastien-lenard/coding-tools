---
status: active  
date: 2026-10-19
---
<!-- docs/designs/unit_test_pipeline.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 0002: Automated Unit Test & Remediation Pipeline Design v0.1

This document details the multi-stage execution pipeline implemented by `batch-unit-test` and `unit_test_orchestrator`, including pre-flight checks, SPDX compliance auto-correction, runtime workspace guarding, tri-state outcomes, and prioritized remediation gates.

---

## Pipeline Architecture & Data Flow

When `batch-unit-test` runs against a target source file, it executes up to **5 iterations** per file. Each iteration follows a structured sequence of pre-flight checks, test execution (including runtime workspace guard checks), and prioritized remediation across all validation stages:

```
[Start Iteration]
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ PRE-FLIGHT CHECKS & SPDX COMPLIANCE                         │
│ 1. Run `workspace_stamper` preemptively on test file        │
│    - Logs mutation status if headers added/corrected        │
│ 2. Static Validation Checks (Priority Ordered):             │
│    - (1) Code Length Check (> 5 lines)                      │
│    - (2) Syntax Validity Check (ast.parse)                  │
│    - (3) Static AST Check for `tmp_path` usage              │
│    - (4) SPDX Header Check                                  │
└──────┬──────────────────────────────────────────────────────┘
       │
       ├─► [PRE-FLIGHT FAILED / UNRESOLVED] ──► Query LLM Directly with Priority Fix Instructions
       │                                         (Bypasses pytest if static pre-checks fail)
       │
       └─► [PRE-FLIGHT PASSED] ─────────────► Proceed to Stage 1: Pytest & Coverage
                                                 │
                                                 ▼
┌──────────────────────────────────────────────┐
│ STAGE 1: Pytest & Coverage Analysis          │
│ - Run pytest with --cov and term-missing     │
│ - Check for collection/syntax errors         │
│ - Run `workspace_guard` runtime check        │
│   (Option 2: Detect unauthorized file        │
│    pollution outside `tmp_path`)             │
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

3. **Pre-Flight Execution Gating**:
   - `workspace_stamper` runs automatically before any test execution to guarantee header compliance.
   - If static pre-checks (1–4) fail and cannot be auto-corrected, pytest is **not** run; control delegates directly to the LLM remediation loop with precise error instructions.

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