# tests/conftest.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Global test fixtures and testing configuration."""

import pytest


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
