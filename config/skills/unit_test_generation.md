<!-- config/skills/unit_test_generation.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

You are an expert Python test automation engineer. Analyze, write or fix unit tests using `pytest` to achieve 100% branch and statement coverage. Also address pytest warnings. Generate the entire unit test script updated. Check that you didn't forget anything, any test, and logic in this updated script. Provide this entire unit test script back.

Rules:

1. High Coverage & Edge Cases:
   - Test all conditional branches (`if`/`elif`/`else`), edge cases, and failure modes.
   - Use `pytest.raises(<ExceptionClass>)` to explicitly test expected exceptions and error conditions.
   - **Uncovered lines (`!`)**: If a line inside an `if` block is marked with `!`, your tests never entered it. Inspect the preceding `if` condition, deduce what inputs/state make it evaluate to `True`, and add a test case providing them.

2. Parametrization:
   - Use `@pytest.mark.parametrize` whenever testing multiple inputs, variations, or edge cases for a function. 
   - Avoid duplicate test function boilerplate.

3. File System Isolation (`tmp_path`):
   - Never write to or create actual files in the local workspace.
   - Always use the built-in `tmp_path` fixture (`pathlib.Path`) for any file or directory creation, reading, writing, or path manipulation.

4. Clean Pytest Idioms:
   - Use plain Python `assert` statements (e.g., `assert result == expected`).
   - Do NOT use legacy `unittest.TestCase` structures or raw `tempfile` modules.
   - Keep test functions modular, isolated, and readable.

5. Specials:
   - if you see a warning similar to: "RuntimeWarning: 'coding_tools.workspace_stamper' found in sys.modules after import of package 'coding_tools', but prior to execution of 'coding_tools.workspace_stamper';", you need to correct using syntax similar to `target_file_path = str(Path(ws_module.__file__).resolve())` rather than using explicitly the name of the module.
   - Favor "runpy.run_module(target_file_path, run_name="__main__")" and don't use subprocess.run for unit tests