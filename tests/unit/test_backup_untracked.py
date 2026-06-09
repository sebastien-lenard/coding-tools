# tests/unit/test_backup_untracked.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit test suite validating the untracked code backup workflows."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from coding_tools.backup_untracked import UntrackedBackupManager, main
from src.coding_tools import backup_untracked

# =====================================================================
# SYSTEM FIXTURES
# =====================================================================


@pytest.fixture
def setup_mock_project(tmp_path: Path) -> dict[str, Path]:
    """Set up a testing environment mimicking structural system paths."""
    project_dir = tmp_path / "my_project"
    output_dir = tmp_path / "my_backups"

    project_dir.mkdir()
    output_dir.mkdir()

    secret_file = project_dir / ".env"
    secret_file.write_text("API_KEY=12345", encoding="utf-8")

    secret_folder = project_dir / "secrets"
    secret_folder.mkdir()
    nested_file = secret_folder / "token.json"
    nested_file.write_text('{"token": "abc"}', encoding="utf-8")

    unrelated_project_file = project_dir / "main.py"
    unrelated_project_file.write_text("print('hello')", encoding="utf-8")

    pre_existing_backup_file = output_dir / "old_backup.txt"
    pre_existing_backup_file.write_text("dont touch", encoding="utf-8")

    config_file = project_dir / ".git_untracked_to_save"
    config_content = f"{output_dir.as_posix()}\n.env\nsecrets/\nmissing_file.txt\n"
    config_file.write_text(config_content, encoding="utf-8")

    return {
        "project_dir": project_dir,
        "output_dir": output_dir,
        "secret_file": secret_file,
        "nested_file": nested_file,
        "unrelated_project_file": unrelated_project_file,
        "pre_existing_backup_file": pre_existing_backup_file,
    }


# =====================================================================
# STRUCTURAL INITIALIZATION VALIDATION
# =====================================================================


def test_pydantic_enforces_directory_existence_on_init() -> None:
    """Verifies that non-existent directory targets fail Pydantic validation."""
    with pytest.raises(ValidationError):
        UntrackedBackupManager(project_path=Path("this/path/does/not/exist/anywhere"))


# =====================================================================
# WORKFLOW EXECUTION FUNCTIONAL TESTS
# =====================================================================


def test_backup_copies_files_and_folders_correctly(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies targets specified within config map into storage paths."""
    proj = setup_mock_project

    manager = UntrackedBackupManager(project_path=proj["project_dir"], verbose=True)
    with caplog.at_level("WARNING"):
        assert manager.execute() is True

    backup_folders = [p for p in proj["output_dir"].iterdir() if p.is_dir()]
    assert len(backup_folders) == 1

    generated_backup_dir = backup_folders[0]
    assert "backup_my_project_" in generated_backup_dir.name

    copied_env = generated_backup_dir / ".env"
    copied_json = generated_backup_dir / "secrets" / "token.json"

    assert copied_env.exists()
    assert copied_env.read_text(encoding="utf-8") == "API_KEY=12345"
    assert copied_json.exists()
    assert copied_json.read_text(encoding="utf-8") == '{"token": "abc"}'
    assert "Skipped (Not Found): missing_file.txt" in caplog.text


def test_no_deletions_occur_during_backup(setup_mock_project: dict[str, Path]) -> None:
    """Guarantees historical code assets remain intact during read executions."""
    proj = setup_mock_project

    manager = UntrackedBackupManager(project_path=proj["project_dir"], verbose=False)
    assert manager.execute() is True

    assert proj["secret_file"].exists()
    assert proj["nested_file"].exists()
    assert proj["unrelated_project_file"].exists()
    assert (
        proj["unrelated_project_file"].read_text(encoding="utf-8") == "print('hello')"
    )
    assert proj["pre_existing_backup_file"].exists()


def test_missing_config_file_logs_error_and_returns_false(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validates proper logging feedback assertions when configurations breaks."""
    empty_dir = tmp_path / "empty_project"
    empty_dir.mkdir()

    manager = UntrackedBackupManager(project_path=empty_dir, verbose=False)

    with caplog.at_level("ERROR"):
        execution_status = manager.execute()
        assert execution_status is False

    assert "Configuration file missing at target" in caplog.text


def test_empty_config_file_returns_false(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensures empty configuration targets return False and log error states."""
    project_dir = tmp_path / "empty_config_project"
    project_dir.mkdir()
    config_file = project_dir / ".git_untracked_to_save"
    config_file.write_text("# Only comments here\n\n", encoding="utf-8")

    manager = UntrackedBackupManager(project_path=project_dir)
    with caplog.at_level("ERROR"):
        assert manager.execute() is False
    assert "is completely empty." in caplog.text


def test_config_file_read_permission_error_returns_none(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensures permission blockers on config files gracefully fail executions."""
    proj = setup_mock_project
    manager = UntrackedBackupManager(project_path=proj["project_dir"])

    with patch.object(Path, "read_text", side_effect=PermissionError):
        with caplog.at_level("ERROR"):
            assert manager.execute() is False
        assert "Failed to securely read configuration file" in caplog.text


def test_config_file_missing_on_read_throws_exception(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validates mid-flight file removal scenario hitting FileNotFoundError branch."""
    proj = setup_mock_project
    manager = UntrackedBackupManager(project_path=proj["project_dir"])

    with patch.object(Path, "read_text", side_effect=FileNotFoundError):
        with caplog.at_level("ERROR"):
            assert manager.execute() is False
        assert "Failed to securely read configuration file" in caplog.text


def test_uncreatable_output_base_directory_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensures uncreatable destination base targets abort safely."""
    proj = setup_mock_project
    config_file = proj["project_dir"] / ".git_untracked_to_save"
    # Overwrite config file to use an impossible uncreatable target path
    config_file.write_text("/uncreatable_root_dir_xyz/backup\n.env", encoding="utf-8")

    manager = UntrackedBackupManager(project_path=proj["project_dir"])
    with patch.object(Path, "mkdir", side_effect=PermissionError):
        with caplog.at_level("ERROR"):
            assert manager.execute() is False
        assert "Backup base destination path is invalid or uncreatable" in caplog.text


def test_copy_item_shutil_exception_logs_error(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validates resilience against unexpected IO failures during file copy phases."""
    proj = setup_mock_project
    manager = UntrackedBackupManager(project_path=proj["project_dir"])

    with patch("shutil.copy2", side_effect=PermissionError):
        with caplog.at_level("ERROR"):
            assert manager.execute() is True  # Main orchestrator skips over errors
        assert "IO Failure tracking copy targets for" in caplog.text


def test_copy_item_unsupported_file_type(
    setup_mock_project: dict[str, Path],
) -> None:
    """Forces execution down the branch where item is neither a file nor directory."""
    proj = setup_mock_project
    manager = UntrackedBackupManager(project_path=proj["project_dir"])

    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = False
    mock_path.is_dir.return_value = False

    with patch.object(Path, "__truediv__", return_value=mock_path):
        assert manager._copy_item("exotic_pipe_stream", Path("destination")) is True


def test_main_gateway_execution_success(tmp_path: Path) -> None:
    """Verifies that the CLI gateway entry point terminates correctly on success."""
    project_dir = tmp_path / "cli_project"
    output_dir = tmp_path / "cli_backup"
    project_dir.mkdir()
    output_dir.mkdir()

    config_file = project_dir / ".git_untracked_to_save"
    config_file.write_text(f"{output_dir.as_posix()}\n", encoding="utf-8")

    test_args = ["backup_untracked.py", str(project_dir), "-v"]
    with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_main_gateway_execution_failure() -> None:
    """Verifies that the CLI gateway flags systemic errors with status exit code 1."""
    test_args = ["backup_untracked.py", "non_existent_directory_target"]
    with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_script_execution_entrypoint(tmp_path: Path) -> None:
    """Asserts execution coverage over the primary standard file entrypoint block.

    Uses an isolated subprocess invocation to cleanly evaluate module execution
    without polluting the parent testing process architecture or mutating state.
    """
    script_path = Path(backup_untracked.__file__)

    # Set up a minimal valid project space so the real main executes smoothly
    project_dir = tmp_path / "entrypoint_project"
    output_dir = tmp_path / "entrypoint_backup"
    project_dir.mkdir()
    output_dir.mkdir()

    config_file = project_dir / ".git_untracked_to_save"
    config_file.write_text(f"{output_dir.as_posix()}\n", encoding="utf-8")

    # Run the script as a direct executable module under the current Python runtime
    # Note: Subprocess execution required to conduct CLI execution (although another
    # way might be better)
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script_path), str(project_dir)],
        capture_output=True,
        text=True,
        check=False,
    )

    # A zero exit code ensures the module successfully entered the __main__ block
    assert result.returncode == 0
