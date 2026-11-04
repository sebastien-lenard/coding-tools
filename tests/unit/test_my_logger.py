# tests/unit/test_my_logger.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for logger."""

import logging
from pathlib import Path

import pytest

from coding_tools import my_logger
from coding_tools.my_logger import (
    BANNED_WORDS,
    MyLogger,
    _clean,
)


def test_clean() -> None:
    """Test text sanitization removes banned words."""
    text = "This workflow execution engine ran successfully!"
    cleaned = _clean(text)
    for word in BANNED_WORDS:
        assert word not in cleaned.lower()
    assert "This" in cleaned


def test_clean_with_banned_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test text sanitization when BANNED_WORDS contains items."""
    monkeypatch.setitem(BANNED_WORDS, "workflow", None)
    text = "This workflow execution engine ran successfully!"
    cleaned = _clean(text)
    assert "workflow" not in cleaned.lower()
    assert "This" in cleaned


@pytest.mark.parametrize(
    ("target", "full_path", "expected"),
    [
        (None, False, ""),
        (None, True, ""),
        ("", False, ""),
        ("", True, ""),
        (Path("script.py"), False, "script: "),
        (Path("script.py"), True, "script.py: "),
        (Path("folder") / "script.py", False, "script: "),
        (Path("folder") / "script.py", True, f"{Path('folder') / 'script.py'}: "),
        (Path("other.txt"), False, "other.txt: "),
        (Path("other.txt"), True, "other.txt: "),
    ],
)
def test_format_target(
    target: str | Path | None,
    full_path: bool,
    expected: str,
) -> None:
    """Test target formatting handles paths and extensions correctly."""
    assert MyLogger._format_target(target, full_path=full_path) == expected


def test_format_target_directory(tmp_path: Path) -> None:
    """Test target formatting returns empty string for directories."""
    assert MyLogger._format_target(tmp_path) == ""
    assert MyLogger._format_target(tmp_path, full_path=True) == ""


def test_project_logger_methods(caplog: pytest.LogCaptureFixture) -> None:
    """Test all MyLogger logging methods and output generation."""
    logger = my_logger.logger("test_logger")

    with caplog.at_level(logging.INFO):
        logger.start(
            "Test process workflow",
            target="my_script.py",
            detail_key="detail_value",
        )
        logger.progress("my_script.py", "running", "fine", full_path=True)
        logger.progress(None, "running")
        logger.end("Test process", target="my_script.py")
        logger.warning(
            target="my_script.py",
            message="Watch out workflow",
            full_path=True,
        )
        logger.error(target="my_script.py", message="Fatal error", full_path=True)
        logger.error(target="my_script.py", message="Exception trace")

        logger.summary_line(
            title="Compact",
            headers=["Col1"],
            values=["Val1"],
        )

        class DummyRow:
            def __init__(self, name: str) -> None:
                self.name = name

        logger.summary_table(
            title="Stats",
            columns={"name": "Name"},
            rows=[{"name": "Alice"}, DummyRow("Bob")],
            formatters={"name": lambda x: x.upper()},
        )

    assert len(caplog.records) > 0


def test_setup_logging() -> None:
    """Test that setup_logging configures the root logger level to INFO."""
    my_logger.setup()
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], logging.StreamHandler)


def test_project_logger_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Test that MyLogger.exception captures messages and tracebacks."""
    logger = my_logger.logger("test_logger")

    def trigger_error() -> None:
        err_msg = "Something went wrong"
        raise ValueError(err_msg)

    with caplog.at_level(logging.ERROR):
        try:
            trigger_error()
        except ValueError:
            logger.exception(
                "my_script.py",
                message="Failed to process",
                full_path=True,
            )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "Failed to process" in record.message
    assert record.exc_info is not None


def test_run_spin(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that run_spin context manager outputs dots and cleans up."""
    logger = my_logger.logger("test_spin")
    with logger.run_spin("Waiting for API", prefix="test"):
        pass
    captured = capsys.readouterr()
    assert "\n" in captured.out
