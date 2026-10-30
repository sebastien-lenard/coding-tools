<!-- config/skills/basedpyright_correction.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

1. Fix static type warnings.
2. Don't edit code or clear comments or clear docstrings outside of your edits to address the static type warnings.

## Examples of accepted fixes:
```python
y: int = 0
if False:
    y = 10
z = y + 1
```

```python
from typing import Protocol

class Renderable(Protocol):
    def render(self, data: list[int]) -> str:
        ...

class Widget:
    def render(self, data: list[int]) -> str:
        return str(data[0]
```

```python
from typing import Sequence

class Animal:
    pass

class Dog(Animal):
    pass

dogs: list[Dog] = []
animals: Sequence[Animal] = dogs
```

```python
from collections.abc import Callable

def my_decorator[F: Callable[..., int]](func: F) -> F:
    return func

@my_decorator
def add(a: int, b: int) -> int:
    return a + b
```

```python
from typing import TypedDict

class DataDict(TypedDict):
    id: int

def get_data() -> DataDict:
    return {"id": 1}
```

```python
from typing import TypeVar

T = TypeVar("T")

def process(val: T) -> T:
    return val

x: int = process(123)
```

```python
def get_value(data: object) -> str:
    val = getattr(data, "value", None)
    error = getattr(data, "error", None)
    if isinstance(val, str) and not error:
        return val
    return ""
```

```python
from pathlib import Path
import my_io
def write(txt: str, path: Path | str) -> None:
    my_io.write_txt(txt, path)
```    

```python
from collections.abc import Callable

def wrap_func(func: Callable[..., int], *args: object, **kwargs: object) -> int:
    return func(*args, **kwargs)
```
