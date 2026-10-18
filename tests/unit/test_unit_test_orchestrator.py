# tests/unit/test_unit_test_orchestrator.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for unit_test_orchestrator module."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import APIError, ServerError

from coding_tools import unit_test_orchestrator

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class PytestIssueCase:
    """Data class representing a test case for pytest execution issues."""

    pytest_summary: str
    pytest_output_val: str
    is_100: bool
    is_syntax: bool
    allow_gemini: bool
    expected_success: bool
    expected_status: str


def test_is_syntactically_valid() -> None:
    """Test is_syntactically_valid with valid and invalid code."""
    assert unit_test_orchestrator.is_syntactically_valid("x = 1") is True
    assert unit_test_orchestrator.is_syntactically_valid("def invalid(") is False


@patch("coding_tools.unit_test_orchestrator.time.sleep", return_value=None)
@patch("coding_tools.unit_test_orchestrator.gemini_spinner")
def test_call_gemini_with_retry_success(
    mock_spinner: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    """Test call_gemini_with_retry succeeds without errors."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    res = unit_test_orchestrator.call_gemini_with_retry(
        mock_client,
        [],
        {},
        "prefix",
        "msg",
    )
    assert res == mock_response
    mock_spinner.assert_called()
    mock_sleep.assert_not_called()


@patch("coding_tools.unit_test_orchestrator.time.sleep", return_value=None)
@patch("coding_tools.unit_test_orchestrator.gemini_spinner")
def test_call_gemini_with_retry_server_error_retry(
    mock_spinner: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    """Test call_gemini_with_retry retries on 503 and then succeeds."""
    mock_client = MagicMock()
    err = ServerError(
        code=503,
        response_json={"error": {"message": "service unavailable"}},
    )
    mock_response = MagicMock()
    mock_client.models.generate_content.side_effect = [err, mock_response]

    res = unit_test_orchestrator.call_gemini_with_retry(
        mock_client,
        [],
        {},
        "prefix",
        "msg",
    )
    assert res == mock_response
    mock_spinner.assert_called()
    mock_sleep.assert_called_once()


@patch("coding_tools.unit_test_orchestrator.time.sleep", return_value=None)
@patch("coding_tools.unit_test_orchestrator.gemini_spinner")
def test_call_gemini_with_retry_server_error_exhausted(
    mock_spinner: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    """Test call_gemini_with_retry raises exception when retries are exhausted."""
    mock_client = MagicMock()
    err = ServerError(
        code=503,
        response_json={"error": {"message": "service unavailable"}},
    )
    mock_client.models.generate_content.side_effect = [err, err, err]

    with pytest.raises(ServerError):
        unit_test_orchestrator.call_gemini_with_retry(
            mock_client,
            [],
            {},
            "prefix",
            "msg",
        )
    mock_spinner.assert_called()
    assert mock_sleep.call_count == 2


@patch("coding_tools.unit_test_orchestrator.time.sleep", return_value=None)
@patch("coding_tools.unit_test_orchestrator.gemini_spinner")
def test_call_gemini_with_retry_none_response(
    mock_spinner: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    """Test call_gemini_with_retry raises RuntimeError if response is None."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = None

    with pytest.raises(RuntimeError, match="Failed to generate content"):
        unit_test_orchestrator.call_gemini_with_retry(
            mock_client,
            [],
            {},
            "prefix",
            "msg",
        )
    mock_spinner.assert_called()
    mock_sleep.assert_not_called()


def test_execute_workflow_success_no_cache(tmp_path: Path) -> None:
    """Test successful execution flow when cache is disabled or not allowed."""
    dummy_test = tmp_path / "test_dummy.py"
    dummy_test.write_text("def test_dummy(): pass", encoding="utf-8")
    dummy_source = tmp_path / "dummy.py"
    dummy_source.write_text("x = 1", encoding="utf-8")

    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 passed", [], "1 passed in 0.1s", True, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.run_basedpyright_command",
            return_value="bp_output",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_basedpyright_summary",
            return_value="0 errors, 0 warnings, 0 notes",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.run_ruff_command",
            return_value="ruff_output",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.filter_ruff_output",
            return_value="All checks passed!",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.cleanup_files",
        ) as mock_cleanup,
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )

        success, stage_name, status = unit_test_orchestrator.execute_workflow(
            test_file_path=str(dummy_test),
            source_file_path=str(dummy_source),
            allow_gemini=True,
        )

    assert success is True
    assert status == "SUCCESS"
    assert stage_name == "ALL_STAGES"
    mock_cleanup.assert_not_called()


def test_execute_workflow_with_cache(tmp_path: Path) -> None:
    """Test successful execution flow when cache is enabled."""
    dummy_test = tmp_path / "test_dummy.py"
    dummy_test.write_text("def test_dummy(): pass", encoding="utf-8")
    dummy_source = tmp_path / "dummy.py"
    dummy_source.write_text("x = 1", encoding="utf-8")

    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch(
            "coding_tools.unit_test_orchestrator.upload_static_file",
            return_value=MagicMock(),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.validate_file_uris",
            return_value=("config_uri", "conftest_uri", "source_uri"),
        ),
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 passed", [], "1 passed in 0.1s", True, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.run_basedpyright_command",
            return_value="bp_output",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_basedpyright_summary",
            return_value="0 errors, 0 warnings, 0 notes",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.run_ruff_command",
            return_value="ruff_output",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.filter_ruff_output",
            return_value="All checks passed!",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.cleanup_files",
        ) as mock_cleanup,
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=True),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        mock_cached_content = MagicMock()
        mock_cached_content.name = "cache-name"
        mock_client_instance.caches.create.return_value = mock_cached_content

        success, stage_name, status = unit_test_orchestrator.execute_workflow(
            test_file_path=str(dummy_test),
            source_file_path=str(dummy_source),
            allow_gemini=True,
        )

    assert success is True
    assert status == "SUCCESS"
    assert stage_name == "ALL_STAGES"
    mock_cleanup.assert_called_once()


@pytest.mark.parametrize(
    "case",
    [
        PytestIssueCase(
            pytest_summary="error in test",
            pytest_output_val="error occurred",
            is_100=True,
            is_syntax=False,
            allow_gemini=True,
            expected_success=False,
            expected_status="FIXED",
        ),
        PytestIssueCase(
            pytest_summary="1 failed",
            pytest_output_val="failed test",
            is_100=True,
            is_syntax=False,
            allow_gemini=True,
            expected_success=False,
            expected_status="FIXED",
        ),
        PytestIssueCase(
            pytest_summary="1 passed",
            pytest_output_val="passed",
            is_100=False,
            is_syntax=False,
            allow_gemini=True,
            expected_success=False,
            expected_status="FIXED",
        ),
        PytestIssueCase(
            pytest_summary="1 passed",
            pytest_output_val="passed with warning: warn",
            is_100=True,
            is_syntax=False,
            allow_gemini=True,
            expected_success=False,
            expected_status="FIXED",
        ),
        PytestIssueCase(
            pytest_summary="error in test",
            pytest_output_val="error occurred",
            is_100=True,
            is_syntax=False,
            allow_gemini=False,
            expected_success=False,
            expected_status="FAILED",
        ),
        PytestIssueCase(
            pytest_summary="1 failed",
            pytest_output_val="failed test",
            is_100=True,
            is_syntax=False,
            allow_gemini=False,
            expected_success=False,
            expected_status="FAILED",
        ),
        PytestIssueCase(
            pytest_summary="1 passed",
            pytest_output_val="passed",
            is_100=False,
            is_syntax=False,
            allow_gemini=False,
            expected_success=False,
            expected_status="FAILED",
        ),
        PytestIssueCase(
            pytest_summary="1 passed",
            pytest_output_val="passed with warning: warn",
            is_100=True,
            is_syntax=False,
            allow_gemini=False,
            expected_success=False,
            expected_status="FAILED",
        ),
        PytestIssueCase(
            pytest_summary="syntax error",
            pytest_output_val="syntax error details",
            is_100=True,
            is_syntax=True,
            allow_gemini=True,
            expected_success=False,
            expected_status="FIXED",
        ),
    ],
)
def test_execute_workflow_pytest_issues(case: PytestIssueCase) -> None:
    """Test handling of pytest errors, failures, missing coverage, and warnings."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch("coding_tools.unit_test_orchestrator.upload_static_file"),
        patch(
            "coding_tools.unit_test_orchestrator.validate_file_uris",
            return_value=("config_uri", "conftest_uri", "source_uri"),
        ),
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=(
                case.pytest_summary,
                ["1"],
                case.pytest_output_val,
                case.is_100,
                case.is_syntax,
                "syntax_details",
            ),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value=(
                "Some warning" if "warning" in case.pytest_output_val else "None"
            ),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.build_contents_list"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=True,
        ),
        patch("coding_tools.unit_test_orchestrator.cleanup_files"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=True),
        patch(
            "coding_tools.unit_test_orchestrator.Path.read_text",
            return_value="old_content",
        ),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        mock_cached_content = MagicMock()
        mock_cached_content.name = "cache-name"
        mock_client_instance.caches.create.return_value = mock_cached_content

        mock_response = MagicMock()
        mock_response.parsed.code = "def test_fixed(): pass"
        mock_client_instance.models.generate_content.return_value = mock_response

        success, _, status = unit_test_orchestrator.execute_workflow(
            allow_gemini=case.allow_gemini,
        )

    assert success is case.expected_success
    assert status == case.expected_status


def test_execute_workflow_pytest_invalid_gemini_code() -> None:
    """Test handling when Gemini returns invalid code during pytest fixes."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 failed", [], "pytest_output", False, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.build_contents_list"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=False,
        ),
        patch("coding_tools.unit_test_orchestrator.cleanup_files"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False),
        patch(
            "coding_tools.unit_test_orchestrator.Path.read_text",
            return_value="content",
        ),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        mock_response = MagicMock()
        mock_response.parsed.code = "invalid"
        mock_client_instance.models.generate_content.return_value = mock_response

        success, _, status = unit_test_orchestrator.execute_workflow(
            allow_gemini=True,
        )

    assert success is False
    assert status == "FAILED"


def test_execute_workflow_pytest_invalid_gemini_code_with_cache() -> None:
    """Test handling when Gemini returns invalid code with CACHE_ALLOWED = True."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch(
            "coding_tools.unit_test_orchestrator.upload_static_file",
            return_value=MagicMock(),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.validate_file_uris",
            return_value=("config_uri", "conftest_uri", "source_uri"),
        ),
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 failed", [], "pytest_output", False, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.build_contents_list"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=False,
        ),
        patch("coding_tools.unit_test_orchestrator.cleanup_files"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=True),
        patch(
            "coding_tools.unit_test_orchestrator.Path.read_text",
            return_value="content",
        ),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        mock_cached_content = MagicMock()
        mock_cached_content.name = "cache-name"
        mock_client_instance.caches.create.return_value = mock_cached_content

        mock_response = MagicMock()
        mock_response.parsed.code = "invalid"
        mock_client_instance.models.generate_content.return_value = mock_response

        success, _, status = unit_test_orchestrator.execute_workflow(
            allow_gemini=True,
        )

    assert success is False
    assert status == "FAILED"


def test_execute_workflow_pytest_parsed_none() -> None:
    """Test handling when Gemini response.parsed is None during pytest fixes."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 failed", [], "pytest_output", False, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.build_contents_list"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=True,
        ),
        patch("coding_tools.unit_test_orchestrator.cleanup_files"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False),
        patch(
            "coding_tools.unit_test_orchestrator.Path.read_text",
            return_value="content",
        ),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        mock_response = MagicMock()
        mock_response.parsed = None
        mock_client_instance.models.generate_content.return_value = mock_response

        with pytest.raises(ValueError, match="Gemini response did not conform"):
            unit_test_orchestrator.execute_workflow(allow_gemini=True)


def test_execute_workflow_identical_code_aborts() -> None:
    """Test that repeated identical code returns 'No solution'."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch(
            "coding_tools.unit_test_orchestrator.upload_static_file",
            return_value=MagicMock(),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.validate_file_uris",
            return_value=("config_uri", "conftest_uri", "source_uri"),
        ),
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 failed", [], "pytest_output", False, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch("coding_tools.unit_test_orchestrator.run_basedpyright_command"),
        patch(
            "coding_tools.unit_test_orchestrator.parse_basedpyright_summary",
            return_value="1 errors, 0 warnings, 0 notes",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.build_contents_list"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=True,
        ),
        patch("coding_tools.unit_test_orchestrator.cleanup_files"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=True),
        patch(
            "coding_tools.unit_test_orchestrator.Path.read_text",
            return_value="test_content",
        ),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        mock_cached_content = MagicMock()
        mock_cached_content.name = "cache-name"
        mock_client_instance.caches.create.return_value = mock_cached_content

        mock_response = MagicMock()
        mock_response.parsed.code = "test_content"
        mock_client_instance.models.generate_content.return_value = mock_response

        success, _, status = unit_test_orchestrator.execute_workflow(
            allow_gemini=True,
        )
        assert success is False
        assert status == "No solution"


@pytest.mark.parametrize(
    ("allow_gemini", "expected_success", "expected_status"),
    [
        (False, False, "FAILED"),
        (True, False, "FIXED"),
    ],
)
def test_execute_workflow_basedpyright_issues(
    allow_gemini: bool,
    expected_success: bool,
    expected_status: str,
) -> None:
    """Test handling of Basedpyright type-checking issues."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 passed", [], "pytest_output", True, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch("coding_tools.unit_test_orchestrator.run_basedpyright_command"),
        patch(
            "coding_tools.unit_test_orchestrator.parse_basedpyright_summary",
            return_value="1 errors, 0 warnings, 0 notes",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.build_contents_list"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=True,
        ),
        patch("coding_tools.unit_test_orchestrator.cleanup_files"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False),
        patch(
            "coding_tools.unit_test_orchestrator.Path.read_text",
            return_value="content",
        ),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )

        mock_response = MagicMock()
        mock_response.parsed.code = "def test_fixed(): pass"
        mock_client_instance.models.generate_content.return_value = mock_response

        success, _, status = unit_test_orchestrator.execute_workflow(
            allow_gemini=allow_gemini,
        )

    assert success is expected_success
    assert status == expected_status


@pytest.mark.parametrize(
    ("allow_gemini", "expected_success", "expected_status"),
    [
        (False, False, "FAILED"),
        (True, False, "FIXED"),
    ],
)
def test_execute_workflow_ruff_issues(
    allow_gemini: bool,
    expected_success: bool,
    expected_status: str,
) -> None:
    """Test handling of Ruff linting issues."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch("coding_tools.unit_test_orchestrator.run_pytest_command"),
        patch(
            "coding_tools.unit_test_orchestrator.read_local_files",
            return_value=("test_content", "coverage_content", "pytest_output"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 passed", [], "pytest_output", True, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.run_basedpyright_command",
            return_value="bp_output",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_basedpyright_summary",
            return_value="0 errors, 0 warnings, 0 notes",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.run_ruff_command",
            return_value="Found 1 error.",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.filter_ruff_output",
            return_value="Found 1 error.",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.build_contents_list"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=True,
        ),
        patch("coding_tools.unit_test_orchestrator.cleanup_files"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False),
        patch(
            "coding_tools.unit_test_orchestrator.Path.read_text",
            return_value="content",
        ),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )

        mock_response = MagicMock()
        mock_response.parsed.code = "def test_fixed(): pass"
        mock_client_instance.models.generate_content.return_value = mock_response

        success, _, status = unit_test_orchestrator.execute_workflow(
            allow_gemini=allow_gemini,
        )

    assert success is expected_success
    assert status == expected_status


@pytest.mark.parametrize(
    ("exception_to_raise", "expected_status"),
    [
        (
            ServerError(
                code=500,
                response_json={"error": {"message": "server error"}},
            ),
            "API_ERROR",
        ),
        (
            APIError(
                code=400,
                response_json={"error": {"message": "api error"}},
            ),
            "API_ERROR",
        ),
    ],
)
def test_execute_workflow_server_error(
    exception_to_raise: Exception,
    expected_status: str,
) -> None:
    """Test that ServerError / APIError is caught and returns API_ERROR status."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch(
            "coding_tools.unit_test_orchestrator.upload_static_file",
            return_value=MagicMock(),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.validate_file_uris",
            return_value=("config_uri", "conftest_uri", "source_uri"),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.run_pytest_command",
            return_value=None,
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 passed", [], "pytest_output", True, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.gemini_spinner"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=True,
        ),
        patch("coding_tools.unit_test_orchestrator.process_and_save_code"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=True),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        mock_cached_content = MagicMock()
        mock_cached_content.name = "cache-name"
        mock_client_instance.caches.create.side_effect = exception_to_raise

        success, _, status = unit_test_orchestrator.execute_workflow(
            allow_gemini=True,
        )
        assert success is False
        assert status == expected_status


@pytest.mark.parametrize(
    "exception_to_raise",
    [
        OSError("Disk error"),
        ValueError("Value error"),
        subprocess.SubprocessError("Subprocess error"),
    ],
)
def test_execute_workflow_exceptions(
    exception_to_raise: Exception,
) -> None:
    """Test that expected exceptions are correctly propagated."""
    with (
        patch("coding_tools.unit_test_orchestrator.Client") as mock_client_cls,
        patch(
            "coding_tools.unit_test_orchestrator.run_pytest_command",
            side_effect=exception_to_raise,
        ),
        patch(
            "coding_tools.unit_test_orchestrator.parse_pytest_results",
            return_value=("1 passed", [], "pytest_output", False, False, ""),
        ),
        patch(
            "coding_tools.unit_test_orchestrator.extract_pytest_warnings",
            return_value="None",
        ),
        patch(
            "coding_tools.unit_test_orchestrator.load_skill",
            return_value="skill_text",
        ),
        patch("coding_tools.unit_test_orchestrator.gemini_spinner"),
        patch(
            "coding_tools.unit_test_orchestrator.is_valid_gemini_code",
            return_value=True,
        ),
        patch("coding_tools.unit_test_orchestrator.process_and_save_code"),
        patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = (
            mock_client_instance
        )
        with pytest.raises(type(exception_to_raise)):
            unit_test_orchestrator.execute_workflow(allow_gemini=True)
