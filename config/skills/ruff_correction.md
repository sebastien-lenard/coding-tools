<!-- config/skills/ruff_correction.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

You are an expert Python 3.12 developer and static code analysis specialist. Fix all Ruff linting errors and warnings for the provided script, respecting the pyproject.toml configuration. Generate the entire script updated. Check that you didn't forget anything, any logic in this updated script, any docstring, any preexisting logs (info or debug) that can be still useful in this updated script. Provide the full script back.

- Use PEP 695 `type` syntax, `X | Y` union types, `list[T]` / `dict[K, V]` built-in generics.
- Line length: Max 88 characters.
- Ensure the top of the file includes:
# [file relative location, e.g. src/coding_tools/unit_test_ask_llm.py]
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

- Never catch blind `Exception` or `BaseException` unless catching at an outer application CLI/entry boundary.
- Replace generic `except Exception as e:` blocks with specific exception types relevant to the code inside the `try` block (e.g., `FileNotFoundError`, `KeyError`, `ValueError`, `requests.RequestException`).
- When re-raising exceptions, use `raise NewException(...) from err` (`B904`).

- Inside `except` blocks, replace `logger.error(...)` with `logger.exception(...)` so exception tracebacks are recorded automatically.

- Add type hints for all function arguments and return values (`def func(param: int) -> str:`).
- Use `Path` from `pathlib` for file system paths instead of `os.path` (`PTH`).

- Convert manual list/dict building loops into comprehensions or standard functions where appropriate.
- Fix all unused arguments (`ARG`), unused loop variables (`B007`), and shadowed built-ins (`A`).