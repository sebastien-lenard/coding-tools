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
from coding_tools.llm_remediation import WorkflowStatus


def test_evaluate_stage_status() -> None:
    """Test _evaluate_stage_status handles FIXED, FAILED, and other statuses."""
    assert unit_test_orchestrator._evaluate_stage_status(
        WorkflowStatus.FIXED,
        "TestStage",
        "FIXED",
    ) == (False, "TestStage", "FIXED")
    assert unit_test_orchestrator._evaluate_stage_status(
        WorkflowStatus.FAILED,
        "TestStage",
        "ERROR",
    ) == (False, "TestStage", "ERROR")
    assert (
        unit_test_orchestrator._evaluate_stage_status(
            WorkflowStatus.SUCCESS,
            "TestStage",
            "SUCCESS",
        )
        is None
    )


@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
def test_run_stage_chain_pytest_failure(mock_remediator_cls: MagicMock) -> None:
    """Test _run_stage_chain aborts if pytest stage fails."""
    remediator = mock_remediator_cls.return_value
    remediator.run_pytest_stage.return_value = (
        WorkflowStatus.FAILED,
        "Pytest",
        "FAILED",
    )
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        remediator,
        "cache",
        [],
        ctx,
    )
    assert success is False
    assert stage == "Pytest"
    assert status == "FAILED"
    remediator.run_workflow_stage.assert_not_called()


@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
def test_run_stage_chain_basedpyright_failure(
    mock_remediator_cls: MagicMock,
) -> None:
    """Test _run_stage_chain aborts if Basedpyright stage fails."""
    remediator = mock_remediator_cls.return_value
    remediator.run_pytest_stage.return_value = (
        WorkflowStatus.SUCCESS,
        "Pytest",
        "SUCCESS",
    )
    remediator.run_workflow_stage.return_value = (
        WorkflowStatus.FIXED,
        "Basedpyright",
        "FIXED",
    )
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        remediator,
        "cache",
        [],
        ctx,
    )
    assert success is False
    assert stage == "Basedpyright"
    assert status == "FIXED"


@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
def test_run_stage_chain_ruff_failure(mock_remediator_cls: MagicMock) -> None:
    """Test _run_stage_chain aborts if Ruff stage fails."""
    remediator = mock_remediator_cls.return_value
    remediator.run_pytest_stage.return_value = (
        WorkflowStatus.SUCCESS,
        "Pytest",
        "SUCCESS",
    )
    remediator.run_workflow_stage.side_effect = [
        (WorkflowStatus.SUCCESS, "Basedpyright", "SUCCESS"),
        (WorkflowStatus.FAILED, "Ruff", "FAILED"),
    ]
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        remediator,
        "cache",
        [],
        ctx,
    )
    assert success is False
    assert stage == "Ruff"
    assert status == "FAILED"


@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
def test_run_stage_chain_success(mock_remediator_cls: MagicMock) -> None:
    """Test _run_stage_chain succeeds when all stages pass."""
    remediator = mock_remediator_cls.return_value
    remediator.run_pytest_stage.return_value = (
        WorkflowStatus.SUCCESS,
        "Pytest",
        "SUCCESS",
    )
    remediator.run_workflow_stage.return_value = (
        WorkflowStatus.SUCCESS,
        "Stage",
        "SUCCESS",
    )
    ctx = MagicMock()
    success, stage, status = unit_test_orchestrator._run_stage_chain(
        remediator,
        "cache",
        [],
        ctx,
    )
    assert success is True
    assert stage == "ALL_STAGES"
    assert status == "SUCCESS"


@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
@patch("coding_tools.unit_test_orchestrator._run_stage_chain")
@patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=True)
def test_execute_workflow_success_cache(
    mock_run_chain: MagicMock,
    mock_remediator_cls: MagicMock,
) -> None:
    """Test execute_workflow success flow with cache allowed."""
    remediator = mock_remediator_cls.return_value
    remediator.setup_cache.return_value = ("cache_name", ["file1"])
    mock_run_chain.return_value = (True, "ALL_STAGES", "SUCCESS")

    success, stage, status = unit_test_orchestrator.execute_workflow(
        allow_gemini=True,
    )
    assert success is True
    assert stage == "ALL_STAGES"
    assert status == "SUCCESS"
    remediator.client.cleanup_files.assert_called_once_with(
        ["file1"], "test_dummy_target.py",
    )


@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
@patch("coding_tools.unit_test_orchestrator._run_stage_chain")
@patch("coding_tools.unit_test_orchestrator.CACHE_ALLOWED", new=False)
def test_execute_workflow_success_no_cache(
    mock_run_chain: MagicMock,
    mock_remediator_cls: MagicMock,
) -> None:
    """Test execute_workflow success flow without cache allowed."""
    remediator = mock_remediator_cls.return_value
    remediator.setup_cache.return_value = (None, [])
    mock_run_chain.return_value = (True, "ALL_STAGES", "SUCCESS")

    success, _stage, _status = unit_test_orchestrator.execute_workflow()
    assert success is True
    remediator.client.cleanup_files.assert_not_called()


@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
@patch("coding_tools.unit_test_orchestrator._run_stage_chain")
def test_execute_workflow_chain_failure(
    mock_run_chain: MagicMock,
    mock_remediator_cls: MagicMock,
) -> None:
    """Test execute_workflow when stage chain returns success=False."""
    remediator = mock_remediator_cls.return_value
    remediator.setup_cache.return_value = (None, [])
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
@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
def test_execute_workflow_api_errors(
    mock_remediator_cls: MagicMock,
    exc: Exception,
) -> None:
    """Test execute_workflow catches ServerError and APIError."""
    remediator = mock_remediator_cls.return_value
    remediator.setup_cache.side_effect = exc

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
@patch("coding_tools.unit_test_orchestrator.LLMRemediator")
def test_execute_workflow_io_sub_errors(
    mock_remediator_cls: MagicMock,
    exc: Exception,
) -> None:
    """Test execute_workflow propagates OSError, ValueError, SubprocessError."""
    remediator = mock_remediator_cls.return_value
    remediator.setup_cache.side_effect = exc

    with pytest.raises(type(exc)):
        unit_test_orchestrator.execute_workflow()
