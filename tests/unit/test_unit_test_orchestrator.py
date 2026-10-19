# tests/unit/test_unit_test_orchestrator.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for unit_test_orchestrator module."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import APIError, ServerError

from coding_tools import unit_test_orchestrator
from coding_tools.gemini_remediation import WorkflowStatus


def test_evaluate_stage_status() -> None:
    """Test _evaluate_stage_status handles FIXED, FAILED, and other statuses."""
    assert unit_test_orchestrator._evaluate_stage_status(
        WorkflowStatus.FIXED, "TestStage", "FIXED",
    ) == (False, "TestStage", "FIXED")
    assert unit_test_orchestrator._evaluate_stage_status(
        WorkflowStatus.FAILED, "TestStage", "ERROR",
    ) == (False, "TestStage", "ERROR")
    assert unit_test_orchestrator._evaluate_stage_status(
        WorkflowStatus.SUCCESS, "TestStage", "SUCCESS",
    ) is None


@patch("coding_tools.unit_test_orchestrator.run_pytest_stage")
@patch("coding_tools.unit_test_orchestrator.run_workflow_stage")
def test_run_stage_chain_pytest_failure(
    mock_run_workflow: MagicMock,
    mock_run_pytest: MagicMock,
) -> None:
    """Test _run_stage_chain aborts if pytest stage fails."""
    mock_run_pytest.return_value = (WorkflowStatus.FAILED, "Pytest", "FAILED")
    client = MagicMock()
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        client, "cache", [], ctx,
    )
    assert success is False
    assert stage == "Pytest"
    assert status == "FAILED"
    mock_run_workflow.assert_not_called()


@patch("coding_tools.unit_test_orchestrator.run_pytest_stage")
@patch("coding_tools.unit_test_orchestrator.run_workflow_stage")
def test_run_stage_chain_basedpyright_failure(
    mock_run_workflow: MagicMock,
    mock_run_pytest: MagicMock,
) -> None:
    """Test _run_stage_chain aborts if Basedpyright stage fails."""
    mock_run_pytest.return_value = (WorkflowStatus.SUCCESS, "Pytest", "SUCCESS")
    mock_run_workflow.return_value = (WorkflowStatus.FIXED, "Basedpyright", "FIXED")
    client = MagicMock()
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        client, "cache", [], ctx,
    )
    assert success is False
    assert stage == "Basedpyright"
    assert status == "FIXED"


@patch("coding_tools.unit_test_orchestrator.run_pytest_stage")
@patch("coding_tools.unit_test_orchestrator.run_workflow_stage")
def test_run_stage_chain_ruff_failure(
    mock_run_workflow: MagicMock,
    mock_run_pytest: MagicMock,
) -> None:
    """Test _run_stage_chain aborts if Ruff stage fails."""
    mock_run_pytest.return_value = (WorkflowStatus.SUCCESS, "Pytest", "SUCCESS")
    mock_run_workflow.side_effect = [
        (WorkflowStatus.SUCCESS, "Basedpyright", "SUCCESS"),
        (WorkflowStatus.FAILED, "Ruff", "FAILED"),
    ]
    client = MagicMock()
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        client, "cache", [], ctx,
    )
    assert success is False
    assert stage == "Ruff"
    assert status == "FAILED"


@patch("coding_tools.unit_test_orchestrator.run_pytest_stage")
@patch("coding_tools.unit_test_orchestrator.run_workflow_stage")
def test_run_stage_chain_success(
    mock_run_workflow: MagicMock,
    mock_run_pytest: MagicMock,
) -> None:
    """Test _run_stage_chain succeeds when all stages pass."""
    mock_run_pytest.return_value = (WorkflowStatus.SUCCESS, "Pytest", "SUCCESS")
    mock_run_workflow.return_value = (WorkflowStatus.SUCCESS, "Stage", "SUCCESS")
    client = MagicMock()
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        client, "cache", [], ctx,
    )
    assert success is True
    assert stage == "ALL_STAGES"
    assert status == "SUCCESS"


@patch("coding_tools.unit_test_orchestrator.Client")
@patch("coding_tools.unit_test_orchestrator.setup_cache")
@patch("coding_tools.unit_test_orchestrator._run_stage_chain")
@patch("coding_tools.unit_test_orchestrator.cleanup_files")
@patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=True)
def test_execute_workflow_success_cache(
    mock_cleanup: MagicMock,
    mock_run_chain: MagicMock,
    mock_setup_cache: MagicMock,
    mock_client_cls: MagicMock,
) -> None:
    """Test execute_workflow success flow with cache allowed."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_setup_cache.return_value = ("cache_name", ["file1"])
    mock_run_chain.return_value = (True, "ALL_STAGES", "SUCCESS")

    success, stage, status = unit_test_orchestrator.execute_workflow(
        allow_gemini=True,
    )
    assert success is True
    assert stage == "ALL_STAGES"
    assert status == "SUCCESS"
    mock_cleanup.assert_called_once_with(mock_client, ["file1"], "test_dummy_target.py")


@patch("coding_tools.unit_test_orchestrator.Client")
@patch("coding_tools.unit_test_orchestrator.setup_cache")
@patch("coding_tools.unit_test_orchestrator._run_stage_chain")
@patch("coding_tools.unit_test_orchestrator.cleanup_files")
@patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False)
def test_execute_workflow_success_no_cache(
    mock_cleanup: MagicMock,
    mock_run_chain: MagicMock,
    mock_setup_cache: MagicMock,
    mock_client_cls: MagicMock,
) -> None:
    """Test execute_workflow success flow without cache allowed."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_setup_cache.return_value = (None, [])
    mock_run_chain.return_value = (True, "ALL_STAGES", "SUCCESS")

    success, _stage, _status = unit_test_orchestrator.execute_workflow()
    assert success is True
    mock_cleanup.assert_not_called()


@patch("coding_tools.unit_test_orchestrator.Client")
@patch("coding_tools.unit_test_orchestrator.setup_cache")
@patch("coding_tools.unit_test_orchestrator._run_stage_chain")
def test_execute_workflow_chain_failure(
    mock_run_chain: MagicMock,
    mock_setup_cache: MagicMock,
    mock_client_cls: MagicMock,
) -> None:
    """Test execute_workflow when stage chain returns success=False."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_setup_cache.return_value = (None, [])
    mock_run_chain.return_value = (False, "Pytest", "FAILED")

    success, stage, status = unit_test_orchestrator.execute_workflow()
    assert success is False
    assert stage == "Pytest"
    assert status == "FAILED"


@pytest.mark.parametrize(
    "exc",
    [
        ServerError(code=500, response_json={"error": {"message": "server error"}}),
        APIError(code=400, response_json={"error": {"message": "api error"}}),
    ],
)
@patch("coding_tools.unit_test_orchestrator.Client")
@patch("coding_tools.unit_test_orchestrator.setup_cache")
def test_execute_workflow_api_errors(
    mock_setup_cache: MagicMock,
    mock_client_cls: MagicMock,
    exc: Exception,
) -> None:
    """Test execute_workflow catches ServerError and APIError."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_setup_cache.side_effect = exc

    success, stage, status = unit_test_orchestrator.execute_workflow()
    assert success is False
    assert stage == "Pytest/Coverage"
    assert status == "API_ERROR"


@pytest.mark.parametrize(
    "exc",
    [
        OSError("Disk error"),
        ValueError("Value error"),
        subprocess.SubprocessError("Subprocess error"),
    ],
)
@patch("coding_tools.unit_test_orchestrator.Client")
@patch("coding_tools.unit_test_orchestrator.setup_cache")
def test_execute_workflow_io_sub_errors(
    mock_setup_cache: MagicMock,
    mock_client_cls: MagicMock,
    exc: Exception,
) -> None:
    """Test execute_workflow propagates OSError, ValueError, SubprocessError."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_setup_cache.side_effect = exc

    with pytest.raises(type(exc)):
        unit_test_orchestrator.execute_workflow()
