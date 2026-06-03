import pytest
from pydantic import ValidationError

from src.coding_tools.backup_untracked import UntrackedBackupManager

# =====================================================================
# SYSTEM FIXTURES
# =====================================================================


@pytest.fixture
def setup_mock_project(tmp_path):
    """Sets up a testing environment mimicking structural system paths."""
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
    config_content = f"{output_dir.as_posix()}\n.env\nsecrets/\n"
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


def test_pydantic_enforces_directory_existence_on_init():
    with pytest.raises(ValidationError):
        UntrackedBackupManager(project_path="this/path/does/not/exist/anywhere")


# =====================================================================
# WORKFLOW EXECUTION FUNCTIONAL TESTS
# =====================================================================


def test_backup_copies_files_and_folders_correctly(setup_mock_project):
    """Verifies targets specified within config map into storage paths."""
    proj = setup_mock_project

    manager = UntrackedBackupManager(project_path=proj["project_dir"], verbose=True)
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


def test_no_deletions_occur_during_backup(setup_mock_project):
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


def test_missing_config_file_logs_error_and_returns_false(tmp_path, caplog):
    """Validates proper logging feedback assertions when configurations breaks."""
    empty_dir = tmp_path / "empty_project"
    empty_dir.mkdir()

    manager = UntrackedBackupManager(project_path=empty_dir, verbose=False)

    with caplog.at_level("ERROR"):
        execution_status = manager.execute()
        assert execution_status is False

    assert "Configuration file missing at target" in caplog.text
