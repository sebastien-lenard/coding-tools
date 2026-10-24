# tests/unit/test_logger.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for logger."""

import logging
from pathlib import Path

import pytest

from coding_tools.logger import (
    BANNED_WORDS,
    ProjectLogger,
    _sanitize,
    get_project_logger,
    setup_logging,
)


def test_sanitize() -> None:
    """Test text sanitization removes banned words."""
    text = "This workflow execution engine ran successfully!"
    cleaned = _sanitize(text)
    for word in BANNED_WORDS:
        assert word not in cleaned.lower()
    assert "This" in cleaned


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (None, ""),
        ("", ""),
        (Path("script.py"), "script: "),
        ("folder/script.py", "script: "),
        (Path("other.txt"), "other.txt: "),
    ],
)
def test_format_target(target: str | Path | None, expected: str) -> None:
    """Test target formatting handles paths and extensions correctly."""
    assert ProjectLogger._format_target(target) == expected


def test_project_logger_methods(caplog: pytest.LogCaptureFixture) -> None:
    """Test all ProjectLogger logging methods and output generation."""
    logger = get_project_logger("test_logger")

    with caplog.at_level(logging.INFO):
        logger.start(
            "Test process workflow",
            target="my_script.py",
            detail_key="detail_value",
        )
        logger.progress("my_script.py", "running", "fine")
        logger.progress(None, "running")
        logger.end("Test process", target="my_script.py")
        logger.warning(target="my_script.py", message="Watch out workflow")
        logger.error(target="my_script.py", message="Fatal error")

        logger.summary_table(
            title="Summary",
            headers=["Col1", "Col2"],
            rows=[
                ["A", "B"],
                ["C", "D"],
            ],
        )

        logger.summary_line(
            title="Compact",
            headers=["Col1"],
            values=["Val1"],
        )

    assert len(caplog.records) > 0


def test_setup_logging() -> None:
    """Test that setup_logging configures the root logger level to INFO."""
    setup_logging()
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], logging.StreamHandler)
