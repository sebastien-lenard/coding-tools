<!-- config/skills/docstring_enhancer.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

1. If the .py file doesn't have a module header docstring, pen the module docstring.
2. If code blocks (classes, functions, methods) don't have docstrings, pen docstrings.
3. If blocks have mismatched or outdated docstrings, fix docstrings.
4. If blocks have incomplete docstrings, fix docstrings. An incomplete docstring can lack (a) key info for debugging the bloc, (b) key info for projects that use the block, (c) edge cases (e.g. when block skips part of its process), (d) needed states, (e) files/db writing access, (f) internet/api access, (g) API keys, (h) commands with their options if any (e.g. pytest with coverage annotations), and (i) any other type of key info you find when scanning the blocks.
5. If docstrings don't use telegraphic writing style, rewrite them in telegraphic style, but making sure all key info is in docstring (use more than 3-4 lines for complex blocks). Opt for words with 1 or 2 syllables, e.g. use, read, cross, run, get, catch, done, audit, scan, clear, yield, check, tip, fill, match, fit, print, pen, bad, input, output, lead, base, fix, apply, system, rules, plug, chain, bridge, mark, start, end, set up, assess, save, store, state, sync, change, edit, summary, param, stats, data, list, repo, tag, item, step-by-step, format, rank, wrap, clean, spread, merge. Use no or few adverbs and adjectives, only when they make the meaning more clear.
6. Don't edit code or clear comments outside of docstrings.

## Examples of accepted pens:

```python
# File header comments (to keep). 1st line: relative file path
# other lines: license comments and flags for automation

"""String tools for text ops.

Safe helpers for base text types.
"""

from enum import Enum


class StringType(Enum):
    """Type of string, EMPTY or NOT_EMPTY."""

    EMPTY = "Empty"
    NOT_EMPTY = "Not empty"

def my_str(txt: object | None) -> str:
    """Cast obj to str or give empty str if null."""
    return str(txt) if txt else ""
```

```python
def check_temp_fixture(
        self,
        test_file_path: str | Path,
    ) -> tuple[bool, list[str]]:
    """Scan test file AST to spot file writing outside tmp_path.

    False if code don't use of pytest's temporary path fixture.
    """
```

```python
def get_response(
        self,
        contents_list: list[object]
    ) -> BaseModel:
    """Call LLM API and check response against Pydantic schema.

    503 retry logic, error after N retries.
    """
```

```python
def run(
    test_file_path: str = "tests/unit/test_dummy_target.py",
    source_file_path: str = "src/coding_tools/dummy_target.py",
) -> tuple[bool, str, str]:
    """Write unit tests and fix pyright and lint/ruff warnings.
    
    Runs pytest with coverage annotations, based-pyright, ruff --fix. Command output
    files saved in .unit-test-tmp. Calls LLM API stepwise, with dynamic prompting
    and task priorities. If a step pass, overwrites unit test file in project. 
    """
```

```python
class Work(BaseModel):
    """Spot banned writing of files by unit tests and fix.
    
    Static audit (AST) and snapshot diff during pytest runs. LLM API calls. If fix
    passes, overwrites unit test file.
    """
```

```python
class GemAdapter:
    """Google GenAI wrapper meeting LLMClientProtocol.
    
    Ties into google.genai v2. Breaking changes if client.models schemas
    change. Needs API key. Cache not set up.
    """
```