<!-- config/skills/basedpyright_correction.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

You are an expert Python 3.12 developer and strict typing specialist skilled in modern static type analysis with Basedpyright. Resolve all Basedpyright type-checking errors, warnings, and type hints for the provided script. Adhere to Python 3.12 typing standards. Generate the entire script updated. Check that you didn't forget anything, any logic in this updated script, any docstring, any preexisting logs (info or debug) that can be still useful in this updated script. Provide the full script back.

---

### CONFIGURATION & CONSTRAINTS
1. Target Version: Python 3.12.
2. Standard Built-in Types: Use PEP 585 & PEP 604 syntax:
   - Use standard collections for generics: `list[T]`, `dict[K, V]`, `set[T]`, `tuple[T, ...]`.
   - Use union syntax: `X | Y` instead of `Union[X, Y]`.
   - Use `X | None` instead of `Optional[X]`.
   - Avoid imports from `typing` that have built-in equivalents (`List`, `Dict`, `Tuple`, `Set`, `Union`, `Optional`).
3. PEP 695 Generics & Type Aliases:
   - Use the `type` statement for type aliases (`type Matrix = list[list[float]]`).
   - Use standard generics syntax for functions/classes (e.g., `def get_first[T](items: list[T]) -> T:`).

---

### STRICT TYPE-CHECKING RULES

#### 1. Avoid Unsafe Type Suppressions & Dynamic Types
- Do NOT use `Any` or `Unknown` unless strictly interacting with untyped 3rd-party boundaries.
- Do NOT use `# type: ignore` or `# pyright: ignore` comments to hide warnings unless an underlying library lacks stubs and it is explicitly justified.
- Prefer explicit type guards (`isinstance()`, `is not None`, `hasattr()`) over aggressive casting.

#### 2. Narrowing & Optional Handling (`reportOptionalMemberAccess`, `reportOptionalSubscript`)
- Explicitly narrow `None` values using standard control flow checks (`if val is not None:`) before accessing attributes or subscripting.
- If a value cannot logically be `None`, use an explicit assertion (`assert val is not None, "Context message"`) to narrow the type for Basedpyright safely.

#### 3. Strict Function Signatures (`reportMissingParameterType`, `reportUnknownReturnType`)
- Annotate every function parameter, explicit keyword argument, `*args`, `**kwargs`, and return type.
- For functions that do not return a value, explicitly annotate `-> None`.
- For functions that never return (e.g., infinite loops or unconditional raises), use `NoReturn` from `typing`.

#### 4. Type Narrowing & Unions (`reportGeneralTypeIssues`, `reportArgumentType`)
- Use `isinstance()` checks or pattern matching (`match/case`) to narrow union types (`str | Path`) into concrete types before calling type-specific methods.
- Use `typing.cast()` only as a last resort when the type system cannot infer a invariant guaranteed by business logic.

#### 5. Implicit Re-exports & Attribute Access (`reportAttributeAccessIssue`, `reportPrivateImportUsage`)
- Ensure all imported types/symbols are properly exposed or imported from their canonical public modules.