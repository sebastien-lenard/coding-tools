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


def test_context_adapter_process() -> None:
    """Test ContextAdapter.process handles base context, self.extra, and call extra."""
    adapter = log.ContextAdapter(logging.getLogger("test_adapter"), {"base_extra": 1})
    with log.log_scope(scope_val=2):
        msg, kwargs = adapter.process("test msg", {"extra": {"call_extra": 3}})
        assert msg == "test msg"
        assert kwargs["extra"]["scope_val"] == 2
        assert kwargs["extra"]["base_extra"] == 1
        assert kwargs["extra"]["call_extra"] == 3


def test_apply_templ_msg_multiline() -> None:
    """Test apply_templ_msg returns early if message contains newline."""
    record = logging.LogRecord(
        name="coding_tools.foo",
        level=logging.INFO,
        pathname="__init__.py",
        lineno=1,
        msg="line1\nline2",
        args=(),
        exc_info=None,
    )
    log.apply_templ_msg(record)
    assert record.msg == "line1\nline2"


def test_apply_templ_msg_full() -> None:
    """Test apply_templ_msg constructs correct message layout."""
    record = logging.LogRecord(
        name="coding_tools.foo",
        level=logging.INFO,
        pathname="__init__.py",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.file = "some/path/file.py"
    record.files_count = 2
    record.step = 1
    record.max_steps = 3
    record.leg = "start"
    record.tool = "pytest"
    log.apply_templ_msg(record)
    assert "file.py" in record.msg
    assert "1/3" in record.msg
    assert "Start" in record.msg
    assert "pytest" in record.msg


def test_drop_traces() -> None:
    """Test drop_traces clears exc_info and exc_text when conditions match."""
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=1,
        msg="err",
        args=(),
        exc_info=(Exception, Exception("test"), None),
    )
    record.exc_text = "some trace"
    logging.getLogger().setLevel(logging.INFO)
    log.drop_traces(record, logging.INFO)
    assert record.exc_info is None
    assert record.exc_text is None


def test_summary_line() -> None:
    """Test summary_line creates expected one-line table string."""
    res = log.summary_line("My Title", ["Col1", "Col2"], ["Val1", "Val2"])
    assert "My Title" in res
    assert "Col1 | Col2" in res
    assert "Val1 | Val2" in res


def test_summary_table() -> None:
    """Test summary_table creates expected multi-line table string with formatters."""
    columns = {"name": "Name", "score": "Score"}
    rows = [
        {"name": "Alice", "score": 10},
        type("Obj", (), {"name": "Bob", "score": 20})(),
    ]
    formatters = {"score": lambda s: f"{s} pts"}
    res = log.summary_table("Stats", columns, rows, formatters=formatters)
    assert "Stats" in res
    assert "Name | Score" in res
    assert "Alice | 10 pts" in res
    assert "Bob | 20 pts" in res
