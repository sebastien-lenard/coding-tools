# tests/conftest.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Global test fixtures and testing configuration."""

import builtins
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

import pytest

from coding_tools import conf
from coding_tools.my_run import RunOutput, RunState

_original_open: Callable[..., IO[Any]] = builtins.open
_original_write_text: Callable[..., int] = Path.write_text
_original_write_bytes: Callable[..., int] = Path.write_bytes
_original_mkdir: Callable[..., None] = Path.mkdir


class WriteOutsideTmpError(RuntimeError):
    """Raised when a test attempts to write outside the tmp_path."""


def _is_allowed(path_val: str | Path | int, allowed: str) -> bool:
    if isinstance(path_val, int):
        return True
    try:
        abs_path: str = str(Path(path_val).resolve())
        return abs_path.startswith(allowed)
    except OSError:
        return False


def _check_write(path_val: str | Path | int, allowed: str) -> None:
    if not _is_allowed(path_val, allowed):
        msg = f"Write outside tmp_path: {path_val}"
        raise WriteOutsideTmpError(msg)


class MockAPIError(Exception):
    """Global mock replacement for APIError."""

    def __init__(
        self,
        message: str | None = None,
        code: int = 400,
        status: str = "INVALID",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class MockServerError(Exception):
    """Global mock replacement for ServerError."""

    def __init__(self, message: str | None = None, code: int = 503) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def dummy_run_output() -> RunOutput:
    """Fake RunOutput for tests."""
    return RunOutput(func="dummy", status=RunState.PRESTART)


@pytest.fixture(autouse=True)
def guard_fs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard file system writes to ensure tests only write within tmp_path."""
    allowed: str = str(tmp_path.resolve())

    def patched_open(
        file: str | Path | int,
        *args: object,
        **kwargs: object,
    ) -> IO[Any]:
        mode_arg = args[0] if args else kwargs.get("mode", "r")
        mode = str(mode_arg)
        if any(w in mode for w in ("w", "a", "x", "+")):
            _check_write(file, allowed)
        return _original_open(file, *args, **kwargs)

    def patched_write_text(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> int:
        _check_write(self, allowed)
        return _original_write_text(self, data, encoding=encoding, errors=errors)

    def patched_write_bytes(self: Path, data: bytes) -> int:
        _check_write(self, allowed)
        return _original_write_bytes(self, data)

    def patched_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        _check_write(self, allowed)
        return _original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(builtins, "open", patched_open)
    monkeypatch.setattr(Path, "write_text", patched_write_text)
    monkeypatch.setattr(Path, "write_bytes", patched_write_bytes)
    monkeypatch.setattr(Path, "mkdir", patched_mkdir)


@pytest.fixture(scope="session")
def tmp_conf_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a fresh temporary conf directory for the test session.

    Copy the project conf folder. Copy .example files to their base filename
    (e.g., skill.md.example -> skill.md), overwrite any existing files.
    """
    conf_dir = conf.conf_dir()
    tmp_conf = tmp_path_factory.mktemp("shared_conf") / conf.conf_folder()

    if conf_dir.exists():
        shutil.copytree(conf_dir, tmp_conf, dirs_exist_ok=True)
        for file in tmp_conf.glob(f"**/*{conf.example_ext()}"):
            shutil.copy2(file, file.with_suffix(""))

    return tmp_conf


@pytest.fixture(autouse=True)
def mock_conf_dir(tmp_conf_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock conf_dir().

    Make sure that any call points to a temporary path, where the .example files from
    the real conf dir have been copied to non .example files, usable for tests
    (github actions).
    """
    monkeypatch.setattr("coding_tools.conf.conf_dir", lambda: tmp_conf_dir)


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Assign 'unit' marker to any test without 'e2e' or 'integration' markers."""
    for item in items:
        has_other_marker = any(
            item.get_closest_marker(name) for name in ["e2e", "integration"]
        )

        if not has_other_marker:
            item.add_marker(pytest.mark.unit)
