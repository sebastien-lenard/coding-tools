# tests/unit/test_llm_remediation.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for llm_remediation.py achieving 100% coverage."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from coding_tools.gemini_client import TestGenerationResponse as TGResponse
from coding_tools.llm_remediation import (
    LLMRemediator,
    StageConfig,
    WorkflowContext,
    WorkflowStatus,
)


def test_workflow_status_enum() -> None:
    """Test workflow status enum values."""
    assert WorkflowStatus.SUCCESS.name == "SUCCESS"
    assert WorkflowStatus.FAILED.name == "FAILED"
    assert WorkflowStatus.FIXED.name == "FIXED"


def test_is_syntactically_valid() -> None:
    """Test syntax validation helper."""
    remediator = LLMRemediator(client=MagicMock())
    assert remediator.is_syntactically_valid("x = 1") is True
    assert remediator.is_syntactically_valid("def invalid_syntax(") is False


def test_llm_remediator_init_default() -> None:
    """Test LLMRemediator initialization with default settings."""
    with patch("coding_tools.llm_remediation.get_llm_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        remediator = LLMRemediator(model_name="test-model")
        assert remediator.client == mock_client
        assert remediator.model_name == "test-model"
        mock_get_client.assert_called_once_with("test-model")


def test_setup_cache() -> None:
    """Test cache setup workflow."""
    mock_client = MagicMock()
    mock_client.setup_cache.return_value = ("cache_name", ["file1"])
    remediator = LLMRemediator(client=mock_client)
    cache_name, files = remediator.setup_cache("source.py", "prefix")
    assert cache_name == "cache_name"
    assert files == ["file1"]
    mock_client.setup_cache.assert_called_once_with("source.py", "prefix")


def test_build_workflow_contents_custom(tmp_path: Path) -> None:
    """Test building custom workflow contents."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("print('test')", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    custom_contents = [MagicMock()]
    stage = StageConfig(
        name="CustomStage",
        run_command=lambda: "output",
        is_success=lambda o: True,
        skill_filename="skill.md",
        build_custom_contents=lambda tp, sp, tc, out: custom_contents,
    )
    remediator = LLMRemediator(client=MagicMock())
    contents = remediator._build_workflow_contents(
        ctx, stage, "print('test')", "output", 1,
    )
    assert contents[0] == custom_contents[0]
    assert len(contents) == 2


def test_build_workflow_contents_default(tmp_path: Path) -> None:
    """Test building default workflow contents."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("print('test')", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="DefaultStage",
        run_command=lambda: "output",
        is_success=lambda o: True,
        skill_filename="skill.md",
        build_custom_contents=None,
    )
    remediator = LLMRemediator(client=MagicMock())
    contents = remediator._build_workflow_contents(
        ctx, stage, "print('test')", "output", 0,
    )
    assert len(contents) == 3


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch("coding_tools.llm_remediation.process_and_save_code")
@patch("coding_tools.llm_remediation.validate_gemini_code", return_value=(True, ""))
@patch("coding_tools.llm_remediation.CACHE_ALLOWED", new=True)
def test_process_llm_remediation_success(
    mock_validate: MagicMock,
    mock_process: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """Test successful LLM remediation processing."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    resp = TGResponse(code="new code", message="fixed")
    mock_client.generate_structured_response.return_value = resp

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx, stage, "cache_name", ["file1"], "output",
    )
    assert status == WorkflowStatus.FIXED
    assert msg == "FIXED"
    mock_client.cleanup_files.assert_called_once_with(["file1"], "pref")
    mock_process.assert_called_once_with("new code", str(test_file), "pref")


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch("coding_tools.llm_remediation.CACHE_ALLOWED", new=True)
def test_process_llm_remediation_exception(
    mock_load: MagicMock, tmp_path: Path,
) -> None:
    """Test LLM remediation when an exception occurs."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    mock_client.generate_structured_response.side_effect = Exception(
        "API error",
    )

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx, stage, "cache_name", ["file1"], "output",
    )
    assert status == WorkflowStatus.FAILED
    assert msg == "FAILED"
    mock_client.cleanup_files.assert_called_once_with(["file1"], "pref")


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch(
    "coding_tools.llm_remediation.validate_gemini_code",
    return_value=(False, "syntax error"),
)
@patch("coding_tools.llm_remediation.CACHE_ALLOWED", new=True)
def test_process_llm_remediation_invalid_code(
    mock_validate: MagicMock, mock_load: MagicMock, tmp_path: Path,
) -> None:
    """Test LLM remediation handling invalid generated code."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    resp = TGResponse(code="bad code", message="fixed")
    mock_client.generate_structured_response.return_value = resp

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx, stage, "cache_name", ["file1"], "output",
    )
    assert status == WorkflowStatus.FAILED
    assert msg == "FAILED"
    mock_client.cleanup_files.assert_called_once_with(["file1"], "pref")


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch("coding_tools.llm_remediation.validate_gemini_code", return_value=(True, ""))
@patch("coding_tools.llm_remediation.process_and_save_code")
@patch("coding_tools.llm_remediation.CACHE_ALLOWED", new=True)
def test_process_llm_remediation_identical_retry_then_success(
    mock_process: MagicMock,
    mock_validate: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """Test retry logic when initial generated code is identical to source."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    resp_identical = TGResponse(code="old code", message="same")
    resp_new = TGResponse(code="new code", message="diff")
    mock_client.generate_structured_response.side_effect = [
        resp_identical,
        resp_new,
    ]

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx, stage, "cache_name", ["file1"], "output",
    )
    assert status == WorkflowStatus.FIXED
    assert msg == "FIXED"
    assert mock_client.generate_structured_response.call_count == 2


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch("coding_tools.llm_remediation.validate_gemini_code", return_value=(True, ""))
@patch("coding_tools.llm_remediation.CACHE_ALLOWED", new=True)
def test_process_llm_remediation_identical_max_reached(
    mock_validate: MagicMock, mock_load: MagicMock, tmp_path: Path,
) -> None:
    """Test max retry limit reached when code remains identical."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    resp_identical = TGResponse(code="old code", message="same")
    mock_client.generate_structured_response.return_value = resp_identical

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx, stage, "cache_name", ["file1"], "output",
    )
    assert status == WorkflowStatus.FAILED
    assert msg == "No solution"
    mock_client.cleanup_files.assert_called_once_with(["file1"], "pref")


def test_run_workflow_stage_success(tmp_path: Path) -> None:
    """Test successful workflow stage execution."""
    ctx = WorkflowContext(
        test_file_path=str(tmp_path / "t.py"),
        source_file_path="s.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: True,
        skill_filename="skill.md",
    )
    remediator = LLMRemediator(client=MagicMock())
    status, name, msg = remediator.run_workflow_stage("cache", [], ctx, stage)
    assert status == WorkflowStatus.SUCCESS
    assert name == "Stage"
    assert msg == "SUCCESS"


def test_run_workflow_stage_fail_no_gemini(tmp_path: Path) -> None:
    """Test workflow stage failure when Gemini is disallowed."""
    ctx = WorkflowContext(
        test_file_path=str(tmp_path / "t.py"),
        source_file_path="s.py",
        prefix="pref",
        allow_gemini=False,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    remediator = LLMRemediator(client=MagicMock())
    status, name, msg = remediator.run_workflow_stage("cache", [], ctx, stage)
    assert status == WorkflowStatus.FAILED
    assert name == "Stage"
    assert msg == "FAILED"


@patch.object(
    LLMRemediator,
    "_process_llm_remediation",
    return_value=(WorkflowStatus.FIXED, "FIXED"),
)
def test_run_workflow_stage_remediation(
    mock_process: MagicMock, tmp_path: Path,
) -> None:
    """Test workflow stage triggering remediation."""
    ctx = WorkflowContext(
        test_file_path=str(tmp_path / "t.py"),
        source_file_path="s.py",
        prefix="pref",
        allow_gemini=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    remediator = LLMRemediator(client=MagicMock())
    status, name, msg = remediator.run_workflow_stage("cache", [], ctx, stage)
    assert status == WorkflowStatus.FIXED
    assert name == "Stage"
    assert msg == "FIXED"
    mock_process.assert_called_once()


def test_run_pytest_stage(tmp_path: Path) -> None:
    """Test pytest runner stage workflow."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("test content", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_gemini=True,
    )
    remediator = LLMRemediator(client=MagicMock())

    with (
        patch("coding_tools.llm_remediation.run_pytest_command") as mock_run_command,
        patch(
            "coding_tools.llm_remediation.read_local_files",
            return_value=("t_code", "s_code", "py_out"),
        ) as mock_read_files,
        patch(
            "coding_tools.llm_remediation.parse_pytest_results",
        ) as mock_parse_results,
        patch(
            "coding_tools.llm_remediation.extract_pytest_warnings",
        ) as mock_extract_warnings,
        patch(
            "coding_tools.llm_remediation.build_contents_list",
        ) as mock_build_contents,
    ):
        mock_parse_results.return_value = ("1 passed", [], 1, True, False, "")
        mock_extract_warnings.return_value = "None"
        res, _name, _msg = remediator.run_pytest_stage(None, [], ctx)
        assert res == WorkflowStatus.SUCCESS
        mock_run_command.assert_called_once_with(
            str(test_file), "source.py", "pref",
        )
        mock_read_files.assert_called_once_with(
            str(test_file), "source.py", "pref",
        )

        mock_parse_results.return_value = (
            "summary",
            [],
            0,
            False,
            True,
            "syntax details",
        )
        with patch.object(
            remediator,
            "run_workflow_stage",
            side_effect=lambda c, u, x, s:
            (s.is_success("py_out"), s.name, "res"),
        ):
            res, _, _ = remediator.run_pytest_stage(None, [], ctx)
            assert res is False

        mock_parse_results.return_value = ("1 passed", [], 1, True, False, "")
        mock_extract_warnings.return_value = "None"
        with patch.object(
            remediator,
            "run_workflow_stage",
            side_effect=lambda c, u, x, s:
            (s.is_success("py_out"), s.name, "res"),
        ):
            res, _, _ = remediator.run_pytest_stage(None, [], ctx)
            assert res is True

        mock_parse_results.return_value = (
            "1 failed",
            ["10"],
            1,
            False,
            False,
            "",
        )
        mock_extract_warnings.return_value = "Some warning"
        with patch.object(
            remediator,
            "run_workflow_stage",
            side_effect=lambda c, u, x, s:
            (s.is_success("py_out"), s.name, "res"),
        ):
            res, _, _ = remediator.run_pytest_stage(None, [], ctx)
            assert res is False

        mock_parse_results.return_value = (
            "summary",
            [],
            0,
            False,
            True,
            "syntax error details",
        )
        stage_config_holder: dict[str, Any] = {}

        def capture_run_workflow(
            c: str | None,
            u: list[str],
            x: WorkflowContext,
            s: StageConfig,
        ) -> tuple[WorkflowStatus, str, str]:
            stage_config_holder["stage"] = s
            return WorkflowStatus.SUCCESS, s.name, "SUCCESS"

        with patch.object(
            remediator,
            "run_workflow_stage",
            side_effect=capture_run_workflow,
        ):
            remediator.run_pytest_stage(None, [], ctx)
            stage = stage_config_holder["stage"]

            contents_syntax = stage.build_custom_contents(
                "t.py", "s.py", "tc", "py_out",
            )
            assert len(contents_syntax) == 3

            mock_parse_results.return_value = (
                "summary",
                [],
                1,
                True,
                False,
                "",
            )
            mock_build_contents.return_value = ["default_part"]
            contents_normal = stage.build_custom_contents(
                "t.py", "s.py", "tc", "py_out",
            )
            assert contents_normal == ["default_part"]
