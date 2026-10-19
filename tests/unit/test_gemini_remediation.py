# [file relative location, e.g. tests/unit/test_gemini_remediation.py]
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for coding_tools.gemini_remediation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ServerError

from coding_tools.gemini_remediation import (
    GeminiRemediationContext,
    StageConfig,
    WorkflowContext,
    WorkflowStatus,
    _build_workflow_contents,
    _process_gemini_remediation,
    call_gemini_with_retry,
    is_syntactically_valid,
    run_pytest_stage,
    run_workflow_stage,
    setup_cache,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_is_syntactically_valid() -> None:
    """Test syntactic validity checking of Python code snippets."""
    assert is_syntactically_valid("x = 1") is True
    assert is_syntactically_valid("x = ") is False


def test_call_gemini_with_retry_success() -> None:
    """Test successful Gemini API call without retries."""
    client = MagicMock()
    mock_response = MagicMock()
    client.models.generate_content.return_value = mock_response

    resp = call_gemini_with_retry(
        client, [], {}, "prefix", "spinner",
    )
    assert resp == mock_response


def test_call_gemini_with_retry_server_error_then_success() -> None:
    """Test Gemini API call succeeding after a 503 server error retry."""
    client = MagicMock()
    mock_response = MagicMock()
    err = ServerError.__new__(ServerError)
    err.code = 503
    client.models.generate_content.side_effect = [err, mock_response]

    with patch("time.sleep") as mock_sleep, \
         patch("coding_tools.gemini_remediation.gemini_spinner"):
        resp = call_gemini_with_retry(
            client, [], {}, "prefix", "spinner",
        )
        assert resp == mock_response
        mock_sleep.assert_called_once_with(2)


def test_call_gemini_with_retry_server_error_max_retries() -> None:
    """Test Gemini API call failing when max retries are reached for 503."""
    client = MagicMock()
    err = ServerError.__new__(ServerError)
    err.code = 503
    client.models.generate_content.side_effect = [err, err, err]

    with patch("time.sleep"), \
         patch("coding_tools.gemini_remediation.gemini_spinner"), \
         pytest.raises(ServerError):
        call_gemini_with_retry(client, [], {}, "prefix", "spinner")


def test_call_gemini_with_retry_server_error_non_503() -> None:
    """Test Gemini API call failing immediately on non-503 server errors."""
    client = MagicMock()
    err = ServerError.__new__(ServerError)
    err.code = 500
    client.models.generate_content.side_effect = err

    with patch("coding_tools.gemini_remediation.gemini_spinner"), \
         pytest.raises(ServerError):
        call_gemini_with_retry(client, [], {}, "prefix", "spinner")


def test_call_gemini_with_retry_response_none() -> None:
    """Test Gemini API call raising RuntimeError when response is None."""
    client = MagicMock()
    client.models.generate_content.return_value = None

    with patch("coding_tools.gemini_remediation.gemini_spinner"), \
         pytest.raises(RuntimeError):
        call_gemini_with_retry(client, [], {}, "prefix", "spinner")


def test_build_workflow_contents_custom() -> None:
    """Test building custom workflow contents using user-provided builder."""
    ctx = WorkflowContext(
        "test.py", "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "",
        is_success=lambda _x: True,
        skill_filename="unit_test_generation.md",
        build_custom_contents=lambda _tp, _sp, _tc, _out: ["custom"],
    )
    res = _build_workflow_contents(ctx, stage, "code", "out", 0)
    assert res == ["custom"]


def test_build_workflow_contents_default_and_identical() -> None:
    """Test building default workflow contents including identical warnings."""
    ctx = WorkflowContext(
        "test.py", "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "",
        is_success=lambda _x: True,
        skill_filename="unit_test_generation.md",
    )
    res = _build_workflow_contents(ctx, stage, "code", "out", 1)
    assert len(res) == 4

    class HasText(Protocol):
        text: str | None

    item = cast("HasText", res[3])
    text_val = item.text
    assert text_val is not None
    assert "IDENTICAL" in text_val


def test_process_gemini_remediation_success(tmp_path: Path) -> None:
    """Test successful processing of Gemini remediation output."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def test_old(): pass", encoding="utf-8")

    ctx = WorkflowContext(
        str(test_file), "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.parsed = MagicMock(
        code="def test_new(): pass", message="fixed",
    )
    client.models.generate_content.return_value = mock_resp

    with patch(
        "coding_tools.gemini_remediation.CACHE_ALLOWED", new=True,
    ), patch(
        "coding_tools.gemini_remediation.cleanup_files",
    ) as mock_cleanup, patch(
        "coding_tools.gemini_remediation.is_valid_gemini_code",
        return_value=True,
    ), patch(
        "coding_tools.gemini_remediation.process_and_save_code",
    ) as mock_save:
        status, _msg = _process_gemini_remediation(
            ctx, stage, GeminiRemediationContext(client, None, [], {}, "out"),
        )
        assert status == WorkflowStatus.FIXED
        mock_save.assert_called_once()
        mock_cleanup.assert_called_once()


def test_process_gemini_remediation_parsed_none(tmp_path: Path) -> None:
    """Test Gemini remediation raising ValueError when parsed is None."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def test_old(): pass", encoding="utf-8")

    ctx = WorkflowContext(
        str(test_file), "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.parsed = None
    client.models.generate_content.return_value = mock_resp

    with patch(
        "coding_tools.gemini_remediation.CACHE_ALLOWED", new=False,
    ), pytest.raises(ValueError, match="Gemini response did not conform"):
        _process_gemini_remediation(
            ctx, stage, GeminiRemediationContext(client, None, [], {}, "out"),
        )


def test_process_gemini_remediation_invalid_code(tmp_path: Path) -> None:
    """Test handling of invalid code returned by Gemini remediation."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def test_old(): pass", encoding="utf-8")

    ctx = WorkflowContext(
        str(test_file), "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.parsed = MagicMock(
        code="invalid code =", message="invalid",
    )
    client.models.generate_content.return_value = mock_resp

    with patch(
        "coding_tools.gemini_remediation.CACHE_ALLOWED", new=True,
    ), patch(
        "coding_tools.gemini_remediation.cleanup_files",
    ) as mock_cleanup, patch(
        "coding_tools.gemini_remediation.is_valid_gemini_code",
        return_value=True,
    ):
        status, _msg = _process_gemini_remediation(
            ctx, stage, GeminiRemediationContext(client, None, [], {}, "out"),
        )
        assert status == WorkflowStatus.FAILED
        mock_cleanup.assert_called_once()


def test_process_gemini_remediation_identical_code_retry_then_success(
    tmp_path: Path,
) -> None:
    """Test remediation retry on identical code followed by success."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def test_old(): pass", encoding="utf-8")

    ctx = WorkflowContext(
        str(test_file), "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    client = MagicMock()
    mock_resp_identical = MagicMock()
    mock_resp_identical.parsed = MagicMock(
        code="def test_old(): pass", message="identical",
    )
    mock_resp_success = MagicMock()
    mock_resp_success.parsed = MagicMock(
        code="def test_new(): pass", message="fixed",
    )
    client.models.generate.side_effect = None
    client.models.generate_content.side_effect = [
        mock_resp_identical,
        mock_resp_success,
    ]

    with patch(
        "coding_tools.gemini_remediation.CACHE_ALLOWED", new=False,
    ), patch(
        "coding_tools.gemini_remediation.is_valid_gemini_code",
        return_value=True,
    ), patch(
        "coding_tools.gemini_remediation.process_and_save_code",
    ) as mock_save:
        status, _msg = _process_gemini_remediation(
            ctx, stage, GeminiRemediationContext(client, None, [], {}, "out"),
        )
        assert status == WorkflowStatus.FIXED
        mock_save.assert_called_once()


def test_process_gemini_remediation_identical_code_abort(
    tmp_path: Path,
) -> None:
    """Test aborting remediation when identical code persists."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def test_old(): pass", encoding="utf-8")

    ctx = WorkflowContext(
        str(test_file), "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.parsed = MagicMock(
        code="def test_old(): pass", message="identical",
    )
    client.models.generate_content.return_value = mock_resp

    with patch(
        "coding_tools.gemini_remediation.CACHE_ALLOWED", new=True,
    ), patch(
        "coding_tools.gemini_remediation.cleanup_files",
    ) as mock_cleanup, patch(
        "coding_tools.gemini_remediation.is_valid_gemini_code",
        return_value=True,
    ):
        status, msg = _process_gemini_remediation(
            ctx, stage, GeminiRemediationContext(client, None, [], {}, "out"),
        )
        assert status == WorkflowStatus.FAILED
        assert msg == "No solution"
        mock_cleanup.assert_called_once()


def test_run_workflow_stage_success() -> None:
    """Test successful execution of a workflow stage without remediation."""
    ctx = WorkflowContext(
        "test.py", "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "output",
        is_success=lambda _x: True,
        skill_filename="unit_test_generation.md",
    )
    status, name, _msg = run_workflow_stage(MagicMock(), None, [], ctx, stage)
    assert status == WorkflowStatus.SUCCESS
    assert name == "TestStage"


def test_run_workflow_stage_failed_no_gemini() -> None:
    """Test workflow stage failure when Gemini remediation is disallowed."""
    ctx = WorkflowContext("test.py", "source.py", "pref", allow_gemini=False)
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "output",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    status, _name, _msg = run_workflow_stage(MagicMock(), None, [], ctx, stage)
    assert status == WorkflowStatus.FAILED


def test_run_workflow_stage_with_remediation() -> None:
    """Test workflow stage execution triggering Gemini remediation."""
    ctx = WorkflowContext(
        "test.py", "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "output",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    with patch(
        "coding_tools.gemini_remediation.load_skill", return_value="skill",
    ), patch(
        "coding_tools.gemini_remediation._process_gemini_remediation",
        return_value=(WorkflowStatus.FIXED, "FIXED"),
    ) as mock_proc:
        status, _name, _msg = run_workflow_stage(
            MagicMock(), "cache_name", [], ctx, stage,
        )
        assert status == WorkflowStatus.FIXED
        mock_proc.assert_called_once()


def test_run_workflow_stage_with_cache_allowed() -> None:
    """Test workflow stage execution when cache is allowed and utilized."""
    ctx = WorkflowContext(
        "test.py", "source.py", "pref", allow_gemini=True,
    )
    stage = StageConfig(
        name="TestStage",
        run_command=lambda: "output",
        is_success=lambda _x: False,
        skill_filename="unit_test_generation.md",
    )
    with patch(
        "coding_tools.gemini_remediation.CACHE_ALLOWED", new=True,
    ), patch(
        "coding_tools.gemini_remediation.load_skill", return_value="skill",
    ), patch(
        "coding_tools.gemini_remediation._process_gemini_remediation",
        return_value=(WorkflowStatus.FIXED, "FIXED"),
    ) as mock_proc:
        status, _name, _msg = run_workflow_stage(
            MagicMock(), "cache_name", [], ctx, stage,
        )
        assert status == WorkflowStatus.FIXED
        call_args = mock_proc.call_args[0][2]
        assert call_args.config_kwargs["cached_content"] == "cache_name"


def test_setup_cache_disabled() -> None:
    """Test cache setup when context caching is disabled."""
    with patch("coding_tools.gemini_remediation.CACHE_ALLOWED", new=False):
        cache, files = setup_cache(MagicMock(), "source.py", "pref")
        assert cache is None
        assert files == []


def test_setup_cache_enabled() -> None:
    """Test cache setup when context caching is enabled."""
    client = MagicMock()
    mock_cache = MagicMock()
    mock_cache.name = "cache_123"
    client.caches.create.return_value = mock_cache

    with patch(
        "coding_tools.gemini_remediation.CACHE_ALLOWED", new=True,
    ), patch(
        "coding_tools.gemini_remediation.upload_static_file",
        return_value=MagicMock(),
    ), patch(
        "coding_tools.gemini_remediation.validate_file_uris",
        return_value=("u1", "u2", "u3"),
    ):
        cache, files = setup_cache(client, "source.py", "pref")
        assert cache == "cache_123"
        assert len(files) == 3


def test_run_pytest_stage() -> None:
    """Test execution and result parsing for the pytest workflow stage."""
    ctx = WorkflowContext(
        "test.py", "source.py", "pref", allow_gemini=True,
    )
    client = MagicMock()

    with patch(
        "coding_tools.gemini_remediation.run_workflow_stage",
        return_value=(
            WorkflowStatus.SUCCESS,
            "Pytest/Coverage",
            "SUCCESS",
        ),
    ) as mock_run:
        status, _name, _msg = run_pytest_stage(client, None, [], ctx)
        assert status == WorkflowStatus.SUCCESS
        assert mock_run.called

    stage_config = mock_run.call_args[0][4]

    with patch(
        "coding_tools.gemini_remediation.run_pytest_command",
    ) as mock_run_cmd, patch(
        "coding_tools.gemini_remediation.read_local_files",
        return_value=("t", "s", "py_out"),
    ) as mock_read:
        assert stage_config.run_command() == "py_out"
        mock_run_cmd.assert_called_once()
        mock_read.assert_called_once()

    with patch(
        "coding_tools.gemini_remediation.parse_pytest_results",
        return_value=("summary", ["m1"], True, True, False, ""),
    ):
        assert stage_config.is_success("output") is True

    with patch(
        "coding_tools.gemini_remediation.parse_pytest_results",
        return_value=("summary", [], True, True, True, "syntax error"),
    ):
        assert stage_config.is_success("output") is False

    with patch(
        "coding_tools.gemini_remediation.parse_pytest_results",
        return_value=("error in summary", [], True, True, False, ""),
    ), patch(
        "coding_tools.gemini_remediation.extract_pytest_warnings",
        return_value="None",
    ):
        assert stage_config.is_success("error output") is False

    with patch(
        "coding_tools.gemini_remediation.parse_pytest_results",
        return_value=("failed", [], True, True, False, ""),
    ), patch(
        "coding_tools.gemini_remediation.extract_pytest_warnings",
        return_value="None",
    ):
        assert stage_config.is_success("failed output") is False

    with patch(
        "coding_tools.gemini_remediation.parse_pytest_results",
        return_value=("summary", [], True, True, False, ""),
    ), patch(
        "coding_tools.gemini_remediation.extract_pytest_warnings",
        return_value="Warning found",
    ):
        assert stage_config.is_success("output") is False

    with patch(
        "coding_tools.gemini_remediation.parse_pytest_results",
        return_value=("summary", [], True, True, True, "details"),
    ):
        custom_contents = stage_config.build_custom_contents(
            "t.py", "s.py", "tc", "py_out",
        )
        assert len(custom_contents) == 3

    with patch(
        "coding_tools.gemini_remediation.parse_pytest_results",
        return_value=("summary", [], True, True, False, ""),
    ), patch(
        "coding_tools.gemini_remediation.build_contents_list",
        return_value=["default"],
    ):
        custom_contents = stage_config.build_custom_contents(
            "t.py", "s.py", "tc", "py_out",
        )
        assert custom_contents == ["default"]
