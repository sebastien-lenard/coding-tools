# tests/unit/test_llm_remediation.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for llm_remediation.py achieving 100% coverage."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

from coding_tools.llm_remediation import (
    LLMRemediator,
    StageConfig,
    WorkflowContext,
    WorkflowStatus,
)


@dataclass
class GeminiResponse:
    """Mock response structure for Gemini API responses."""

    code: str
    message: str = ""


TGResponse = GeminiResponse


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
        allow_llm=True,
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
        ctx,
        stage,
        "print('test')",
        "output",
        0,
    )
    assert contents[0] == custom_contents[0]
    assert len(contents) == 1

    contents_retry = remediator._build_workflow_contents(
        ctx,
        stage,
        "print('test')",
        "output",
        1,
    )
    assert len(contents_retry) == 2


def test_build_workflow_contents_default(tmp_path: Path) -> None:
    """Test building default workflow contents."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("print('test')", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
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
        ctx,
        stage,
        "print('test')",
        "output",
        0,
    )
    assert len(contents) == 2

    contents_retry = remediator._build_workflow_contents(
        ctx,
        stage,
        "print('test')",
        "output",
        1,
    )
    assert len(contents_retry) == 3


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch("coding_tools.llm_remediation.process_and_save_code")
@patch("coding_tools.llm_remediation.validate_llm_code", return_value=(True, ""))
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
        allow_llm=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    mock_client.supports_caching = True
    resp = TGResponse(code="new code", message="fixed")
    mock_client.generate_structured_response.return_value = resp

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx,
        stage,
        "cache_name",
        ["file1"],
        "output",
    )
    assert status == WorkflowStatus.FIXED
    assert msg == "FIXED"
    mock_client.cleanup_files.assert_called_once_with(["file1"], "pref")
    mock_process.assert_called_once_with("new code", str(test_file), "pref")


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
def test_process_llm_remediation_exception(
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """Test LLM remediation when an exception occurs."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    mock_client.supports_caching = True
    mock_client.generate_structured_response.side_effect = Exception(
        "API error",
    )

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx,
        stage,
        "cache_name",
        ["file1"],
        "output",
    )
    assert status == WorkflowStatus.FAILED
    assert msg == "FAILED"
    mock_client.cleanup_files.assert_called_once_with(["file1"], "pref")


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch(
    "coding_tools.llm_remediation.validate_llm_code",
    return_value=(False, "syntax error"),
)
def test_process_llm_remediation_invalid_code(
    mock_validate: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """Test LLM remediation handling invalid generated code."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    mock_client.supports_caching = True
    resp = TGResponse(code="bad code", message="fixed")
    mock_client.generate_structured_response.return_value = resp

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx,
        stage,
        "cache_name",
        ["file1"],
        "output",
    )
    assert status == WorkflowStatus.FAILED
    assert msg == "FAILED"
    mock_client.cleanup_files.assert_called_once_with(["file1"], "pref")


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch("coding_tools.llm_remediation.validate_llm_code", return_value=(True, ""))
@patch("coding_tools.llm_remediation.process_and_save_code")
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
        allow_llm=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    mock_client.supports_caching = False
    resp_identical = TGResponse(code="old code", message="same")
    resp_new = TGResponse(code="new code", message="diff")
    mock_client.generate_structured_response.side_effect = [
        resp_identical,
        resp_new,
    ]

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx,
        stage,
        "cache_name",
        ["file1"],
        "output",
    )
    assert status == WorkflowStatus.FIXED
    assert msg == "FIXED"
    assert mock_client.generate_structured_response.call_count == 2


@patch("coding_tools.llm_remediation.load_skill", return_value="skill instruction")
@patch("coding_tools.llm_remediation.validate_llm_code", return_value=(True, ""))
def test_process_llm_remediation_identical_max_reached(
    mock_validate: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """Test max retry limit reached when code remains identical."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("old code", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
    )
    stage = StageConfig(
        name="Stage",
        run_command=lambda: "output",
        is_success=lambda o: False,
        skill_filename="skill.md",
    )
    mock_client = MagicMock()
    mock_client.supports_caching = True
    resp_identical = TGResponse(code="old code", message="same")
    mock_client.generate_structured_response.return_value = resp_identical

    remediator = LLMRemediator(client=mock_client)
    status, msg = remediator._process_llm_remediation(
        ctx,
        stage,
        "cache_name",
        ["file1"],
        "output",
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
        allow_llm=True,
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


def test_run_workflow_stage_fail_no_llm(tmp_path: Path) -> None:
    """Test workflow stage failure when LLM is disallowed."""
    ctx = WorkflowContext(
        test_file_path=str(tmp_path / "t.py"),
        source_file_path="s.py",
        prefix="pref",
        allow_llm=False,
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
    mock_process: MagicMock,
    tmp_path: Path,
) -> None:
    """Test workflow stage triggering remediation."""
    ctx = WorkflowContext(
        test_file_path=str(tmp_path / "t.py"),
        source_file_path="s.py",
        prefix="pref",
        allow_llm=True,
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


def test_run_pytest_stage_preflight(tmp_path: Path) -> None:
    """Test pytest stage preflight failure and success workflows."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("test content", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
    )
    remediator = LLMRemediator(client=MagicMock())

    with (
        patch(
            "coding_tools.llm_remediation.run_preflight_compliance_and_validation",
            return_value=(False, ["error1"]),
        ),
        patch.object(
            remediator,
            "_process_llm_remediation",
            return_value=(WorkflowStatus.FIXED, "FIXED"),
        ) as mock_remed,
    ):
        status, name, msg = remediator.run_pytest_stage(None, [], ctx)
        assert status == WorkflowStatus.FIXED
        assert name == "Pytest/Coverage"
        assert msg == "FIXED"
        mock_remed.assert_called_once()

    ctx_no_llm = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=False,
    )
    with patch(
        "coding_tools.llm_remediation.run_preflight_compliance_and_validation",
        return_value=(False, ["error1"]),
    ):
        status, name, msg = remediator.run_pytest_stage(None, [], ctx_no_llm)
        assert status == WorkflowStatus.FAILED
        assert name == "Pytest/Coverage"
        assert msg == "FAILED"


def test_run_pytest_stage_command(tmp_path: Path) -> None:
    """Test building pytest run command and workspace guard checks."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("test content", encoding="utf-8")
    ctx = WorkflowContext(
        test_file_path=str(test_file),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
    )
    remediator = LLMRemediator(client=MagicMock())

    with (
        patch("coding_tools.llm_remediation.WorkspaceGuard") as mock_guard_cls,
        patch(
            "coding_tools.llm_remediation.read_local_files",
            return_value=("t_code", "s_code", "py_out"),
        ),
    ):
        mock_guard = mock_guard_cls.return_value
        mock_guard.execute_test_and_guard.side_effect = [(False, ["violation1"])]
        run_cmd = remediator._build_pytest_run_command(ctx)
        res_output = run_cmd()
        assert "Runtime Workspace Guard Violations" in res_output

        mock_guard.execute_test_and_guard.side_effect = [(True, [])]
        res_output_clean = run_cmd()
        assert "Runtime Workspace Guard Violations" not in res_output_clean


def test_run_pytest_stage_evaluation(tmp_path: Path) -> None:
    """Test evaluating pytest success results."""
    ctx = WorkflowContext(
        test_file_path=str(tmp_path / "t.py"),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
    )
    remediator = LLMRemediator(client=MagicMock())
    check_func = remediator._evaluate_pytest_success(ctx)
    with patch("coding_tools.llm_remediation.parse_pytest_results") as mock_parse:
        mock_parse.return_value = ("1 passed", [], True, True, False, "")
        assert check_func("some output") is True

        mock_parse.return_value = ("error", [], True, False, True, "syntax details")
        assert check_func("some output") is False

        mock_parse.return_value = ("1 failed", [], False, False, False, "")
        assert check_func("some output") is False

        mock_parse.return_value = ("error in execution", [], True, False, False, "")
        assert check_func("some output") is False

        mock_parse.return_value = ("1 passed", [], True, True, False, "")
        assert check_func("Runtime Workspace Guard Violations") is False


def test_run_pytest_stage_custom_contents(tmp_path: Path) -> None:
    """Test building custom contents for pytest stage."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("test content", encoding="utf-8")
    remediator = LLMRemediator(client=MagicMock())

    with patch("coding_tools.llm_remediation.parse_pytest_results") as mock_parse:
        mock_parse.return_value = ("error", [], True, False, True, "syntax details")
        custom_content = remediator._build_pytest_custom_contents(
            str(test_file),
            "source.py",
            "test content",
            "py_output",
        )
        assert len(custom_content) == 3

        mock_parse.return_value = ("1 passed", [], True, True, False, "")
        with patch(
            "coding_tools.llm_remediation.build_contents_list",
            return_value=["built"],
        ) as mock_bcl:
            custom_content_ok = remediator._build_pytest_custom_contents(
                str(test_file),
                "source.py",
                "test content",
                "py_output",
            )
            assert custom_content_ok == ["built"]
            mock_bcl.assert_called_once()


def test_run_pytest_stage_success(tmp_path: Path) -> None:
    """Test successful pytest stage execution workflow."""
    ctx = WorkflowContext(
        test_file_path=str(tmp_path / "t.py"),
        source_file_path="source.py",
        prefix="pref",
        allow_llm=True,
    )
    remediator = LLMRemediator(client=MagicMock())

    with (
        patch(
            "coding_tools.llm_remediation.run_preflight_compliance_and_validation",
            return_value=(True, []),
        ),
        patch.object(
            remediator,
            "run_workflow_stage",
            return_value=(WorkflowStatus.SUCCESS, "Pytest/Coverage", "SUCCESS"),
        ) as mock_run_stage,
    ):
        status, name, msg = remediator.run_pytest_stage(None, [], ctx)
        assert status == WorkflowStatus.SUCCESS
        assert name == "Pytest/Coverage"
        assert msg == "SUCCESS"
        mock_run_stage.assert_called_once()
