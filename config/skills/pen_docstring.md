<!-- config/skills/docstring_enhancer.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

1. If the .py file doesn't have a module header docstring, write the module docstring.
2. If code blocks (classes, functions, methods) don't have docstrings, write docstrings.
3. If blocks have mismatched or outdated docstrings, fix docstrings.
4. If blocks have incomplete docstrings, fix docstrings. An incomplete docstring can lack (a) key info for debugging the bloc, (b) key info for projects that use the block, including (c) edge cases (e.g. when block skips part of its process), (d) state requirements, (e) files/db writing access, (f) internet/api access, (g) API keys, (h) commands with their options if any (e.g. pytest with coverage annotations), and (i) any other type of key info you find when scanning the blocks.
5. If docstrings don't use telegraphic writing style, rewrite them in telegraphic style, but making sure all key info is in docstring (use more than 3-4 lines for complex blocks). Adverbs or adjectives only if they change meaning of sentence (e.g. don't write "direct/directly", "safe/safely", "modified", ). Function/method docstrings start with imperative verb. When a word has synonyms, favor the shorter synonym (e.g. "use" over "utilize", "check" over "verify" or "validate", "run" over "execute", "get" over "collect", "edit" over "modify" or "mutate", "yield" over "generate" or "compute", "lead" over "orchestrate", "to fix" over "to correct", "audit" or "scan" over "inspection").
6. Don't change code or erase comments outside of docstrings.

## Examples (Functions & Methods):

### Rejected:
```python
def check_temp_fixture(
        self,
        test_file_path: str | Path,
    ) -> tuple[bool, list[str]]:
    """Inspects the test file AST to ensure test functions use tmp_path for I/O.
    
    Args:
        self: The WorkspaceGuard instance.
        test_file_path (str | Path): The path to the test file.
        prefix (str): Logging prefix string.
        
    Returns:
        tuple[bool, list[str]]: A tuple containing a boolean success flag and list of violations.
    """
```

### Accepted:
```python
def check_temp_fixture(
        self,
        test_file_path: str | Path,
    ) -> tuple[bool, list[str]]:
    """Scan test file AST to spot file writing outside tmp_path.

    False if code don't use of pytest's temporary path fixture.
    """
```

### Rejected:
```python
def get_response(
   self, contents_list: list[object]) -> BaseModel:
    """Generates a structured response from the LLM client.

    This method takes contents and options and queries Gemini.
    """
```

### Accepted:
```python
def get_response(
        self,
        contents_list: list[object]
    ) -> BaseModel:
    """Call LLM API and check response against Pydantic schema.

    503 retry logic, error after N retries.
    """
```

### Rejected:
```python
def run(
    test_file_path: str = "tests/unit/test_dummy_target.py",
    source_file_path: str = "src/coding_tools/dummy_target.py",
) -> tuple[bool, str, str]:
    """Execute complete test generation, type checking, and linting pipeline.
    
    Cleans up remote LLM cache files on completion unless an exception interrupts.
    """
```

### Accepted:
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


## Examples (Modules & Classes):

### Rejected:
```python
class Work(BaseModel):
    """Enforces test file isolation and prevents workspace file pollution by scanning AST nodes.
    
    Attributes:
        project_path (Path): The root path of the project.
    
    Uses AST static inspection and snapshot comparison during live pytest runs.
    """
```

### Accepted:
```python
class Work(BaseModel):
    """Spot banned writing of files by unit tests and fix.
    
    Static audit (AST) and snapshot diff during pytest runs. LLM API calls. If fix
    passes, overwrites unit test file.
    """
```

### Rejected:
```python
class GemAdapter:
    """Client class for gemini api calls satisfying LLMClientProtocol."""
```

### Accepted:
```python
class GemAdapter:
    """Google GenAI wrapper meeting LLMClientProtocol.
    
    Ties into google.genai v2. Breaking changes if client.models schemas
    change. Needs API key. Cache not set up.
    """
```