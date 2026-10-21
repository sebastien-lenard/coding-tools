---
status: active  
date: 2026-10-19
---
<!-- docs/designs/unit_test_pipeline.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 0002: Automated Unit Test & Remediation Pipeline Design v0.1

This document details the multi-stage execution pipeline implemented by `batch-unit-test` and `unit_test_orchestrator`.

---

## Pipeline Architecture & Data Flow

When `batch-unit-test` runs against a target source file, it executes up to **5 iterations** per file. Each iteration runs a strict 3-stage validation and AI remediation sequence:

```
[Start Iteration]
       │
       ▼
┌──────────────────────────────────────────────┐
│ STAGE 1: Pytest & Coverage Analysis          │
│ - Run pytest with --cov and term-missing     │
│ - Check for collection/syntax errors         │
│ - Verify 100% test coverage & zero warnings  │
└──────┬───────────────────────────────────────┘
       │
       ├─► [PASSED] ──► Proceed to Stage 2
       │
       └─► [FAILED] ──► Query Gemini API with coverage hints & errors
                          │
                          ▼
                        Save AI fix to disk (Status: FIXED)
                          │
                          ▼
                        [Next Iteration] (Re-test updated file)

       │
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
                        Save AI fix to disk (Status: FIXED)
                          │
                          ▼
                        [Next Iteration]
       │
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
                        Save AI fix to disk (Status: FIXED)
                          │
                          ▼
                        [Next Iteration]
```

---

## Key Engineering Mechanics

1. **Tri-State Stage Outcomes (`WorkflowStatus`)**:
   - `SUCCESS`: The stage passed all local assertions cleanly without requiring intervention.
   - `FAILED`: The stage failed, and either LLM calls were disabled (`allow_gemini=False`) or the LLM hit a fatal stagnation / exception limit (`No solution`).
   - `FIXED`: Gemini successfully generated a valid, non-identical code fix, which was immediately persisted to disk. This triggers the iteration controller to feed the updated file into the next test cycle.

2. **Progression & Iteration Boundaries**:
   - If a fix is applied during Pytest, the orchestrator returns control so the next iteration validates the new test code from scratch.
   - On the **last allowed iteration** (`max_iterations`), Gemini authorization is disabled (`allow_gemini = False`), serving as a strict read-only audit run to prevent infinite LLM loops.