# tests/unit/test_logger.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for logger."""

import logging

from coding_tools.logger import setup_logging


def test_setup_logging() -> None:
    """Test that setup_logging configures the root logger level to INFO."""
    setup_logging()
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
