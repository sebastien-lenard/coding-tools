<!-- config/templates/cov_tips.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

--- Fix Unit Test Coverage Gaps  ---

### Uncovered Statements
{uncovered_statements_body}

### Unconditional / Partial Branch Jumps
{branch_jumps_body}

--- Uncovered Statement Template ---
- Context:
```python
{context_snippet}
```
- Where: Function `{function_name}`
- Audit: {audit_msg}
- Fix: Yield test inputs or mock state to run the code block

--- Branch Jump Template ---
- Branch context:
```python
{branch_snippet}
```
- Where: Function `{function_name}`
- Audit: {audit}
- Fix: Have tests testing both outcomes of this branch.

--- Missing Coverage Template ---
To do: pen unit tests to cover src file {source_file}