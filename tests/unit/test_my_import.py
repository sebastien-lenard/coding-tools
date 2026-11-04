# tests/unit/test_my_import.py  # noqa: ERA001
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for my_import module."""

import pytest

from coding_tools import my_import


def test_import_module_success() -> None:
    """Test successful module import."""
    mod = my_import.import_module("math")
    assert mod.__name__ == "math"


def test_import_module_error() -> None:
    """Test import module handles ImportError and raises."""
    with pytest.raises(ImportError):
        my_import.import_module("non_existent_module_xyz_123")
