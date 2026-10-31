<!-- config/skills/fix_lint.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

1. Fix lint warnings.
2. Don't edit code or clear comments or clear docstrings outside of your edits to address the lint warnings.

## Examples of accepted fixes:
```python
from pathlib import Path

from coding_tools import my_logger

logger = my_logger.logger(__name__)

def read_txt(path: Path | str) -> str | None:
    """Get text from utf8 file."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.exception(None, f"Failed to read or decode file {path}")
        return None
```

```python
cleaned_users = [process_user(u) for u in raw_users if u.strip() != "admin"]
```

```python
class BadResponseError(Exception):
    """Raised when a webhook or API response is badly formatted."""

def extract_user_id(data: dict) -> int:
    try:
        return data["user_id"]
    except KeyError as err:
        raise InvalidPayloadError("Missing 'user_id' in API response") from err
```

```python
def index[T](items: list[T], key: str) -> dict[str, T]:
    """Indexes a list of objects into a dictionary."""
    result: dict[str, T] = {}

    for item in items:
        if hasattr(item, key):
            k = str(getattr(item, key))
            result[k] = item

    return result


class User:
    """Is a system user."""
    def __init__(self, user_id: str, name: str) -> None:
        """Init user profile."""
        self.user_id = user_id
        self.name = name

    def __repr__(self) -> str:
        """Get user's string."""
        return f"User({self.name})"


users: list[User] = [
    User("u1", "Alice"),
    User("u2", "Bob"),
    User("u3", "Charlie"),
]

user_book: dict[str, User] = index(users, "user_id")
```