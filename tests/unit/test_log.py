# tests/unit/test_log.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for log."""

import logging

import pytest

from coding_tools import log


def test_set_level() -> None:
    """Test set_level sets logger level properly with various verbosity counts."""
    logger = logging.getLogger("test_level")
    log.set_level(logger, -1)
    assert logger.level == logging.WARNING
    log.set_level(logger, 1)
    assert logger.level == logging.INFO
    log.set_level(logger, 10)
    assert logger.level == logging.DEBUG


def test_setup_logging() -> None:
    """Test that setup_logging configures the root logger level to INFO."""
    log.setup()
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], logging.StreamHandler)


def test_project_logger_exception(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that MyLogger.exception captures messages and tracebacks."""
    monkeypatch.setattr(log, "drop_traces", lambda *args, **kwargs: None)
    logger = log.logger("test_logger")

    def trigger_error() -> None:
        err_msg = "Something went wrong"
        raise ValueError(err_msg)

    with caplog.at_level(logging.ERROR):
        try:
            trigger_error()
        except ValueError:
            logger.exception("Failed to process")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "Failed to process" in record.message
    assert record.exc_info is not None


def test_run_spin(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that run_spin context manager outputs dots and cleans up."""
    logger = log.logger("test_spin")
    with log.run_spin(logger, "Waiting for API"):
        pass
    captured = capsys.readouterr()
    assert "\n" in captured.out
