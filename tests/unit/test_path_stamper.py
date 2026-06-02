import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from src.coding_tools import (
    generate_updated_content,
    run_process,
    scan_python_files,
    verify_git_diff,
)

# =====================================================================
# PURE LOGIC TESTS
# =====================================================================


def test_adds_path_comment_to_empty_file():
    new_content, modified = generate_updated_content("", "src/utils/config.py")
    assert modified is True
    assert new_content == "# src/utils/config.py\n"


def test_preserves_shebang_and_coding_header_and_prepends_path():
    content = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nprint('Hello World')\n"
    new_content, modified = generate_updated_content(content, "src/utils/config.py")

    assert modified is True
    expected = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# src/utils/config.py\n"
        "print('Hello World')\n"
    )
    assert new_content == expected


def test_replaces_old_path_with_new_relative_path_safely():
    content = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# /Users/personal/old_project/config.py\n"
        "# Additional metadata info\n"
        "print('Code')\n"
    )
    new_content, modified = generate_updated_content(content, "src/utils/config.py")

    assert modified is True
    expected = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# src/utils/config.py\n"
        "# Additional metadata info\n"
        "print('Code')\n"
    )
    assert new_content == expected


def test_no_modification_if_correct_path_exists():
    content = "#!/usr/bin/env python3\n# src/utils/config.py\nprint('Code')\n"
    new_content, modified = generate_updated_content(content, "src/utils/config.py")
    assert modified is False
    assert new_content == content


def test_scans_deep_folders_and_ignores_non_python_or_venvs(tmp_path):
    # tmp_path is a built-in pytest fixture providing a secure, isolated directory
    src_dir = tmp_path / "src" / "utils"
    venv_dir = tmp_path / ".venv" / "lib"
    src_dir.mkdir(parents=True)
    venv_dir.mkdir(parents=True)

    # Create files to check
    file1 = tmp_path / "src" / "main.py"
    file2 = tmp_path / "src" / "utils" / "config.py"
    ignored_txt = tmp_path / "src" / "notes.txt"
    ignored_venv = tmp_path / ".venv" / "lib" / "site.py"

    for f in [file1, file2, ignored_txt, ignored_venv]:
        f.touch()

    found_files = scan_python_files(tmp_path)

    assert file1 in found_files
    assert file2 in found_files
    assert ignored_txt not in found_files
    assert ignored_venv not in found_files
    assert len(found_files) == 2


# =====================================================================
# GIT DIFF VERIFICATION TESTS
# =====================================================================


def test_returns_true_when_no_changes(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(stdout="", returncode=0))
    monkeypatch.setattr(subprocess, "run", mock_run)

    is_valid, errors = verify_git_diff(Path("/fake/path"))
    assert is_valid is True
    assert len(errors) == 0


def test_returns_true_for_valid_single_comment_addition(monkeypatch):
    valid_diff = (
        "diff --git a/src/main.py b/src/main.py\n"
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -0,0 +1 @@\n"
        "+# src/main.py\n"
    )
    mock_run = MagicMock(return_value=MagicMock(stdout=valid_diff, returncode=0))
    monkeypatch.setattr(subprocess, "run", mock_run)

    is_valid, errors = verify_git_diff(Path("/fake/path"))
    assert is_valid is True
    assert len(errors) == 0


def test_returns_true_for_valid_comment_replacement(monkeypatch):
    replacement_diff = (
        "diff --git a/src/storage/db.py b/src/storage/db.py\n"
        "--- a/src/storage/db.py\n"
        "+++ b/src/storage/db.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-# src/storage/db.py\n"
        "+# src/manuscript_reference_lister/storage/db.py\n"
    )
    mock_run = MagicMock(return_value=MagicMock(stdout=replacement_diff, returncode=0))
    monkeypatch.setattr(subprocess, "run", mock_run)

    is_valid, errors = verify_git_diff(Path("/fake/path"))
    assert is_valid is True
    assert len(errors) == 0


def test_returns_false_if_code_was_deleted_or_modified(monkeypatch):
    invalid_diff = (
        "diff --git a/src/main.py b/src/main.py\n"
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -1,1 +1,2 @@\n"
        "-print('old')\n"
        "+# src/main.py\n"
        "+print('new')\n"
    )
    mock_run = MagicMock(return_value=MagicMock(stdout=invalid_diff, returncode=0))
    monkeypatch.setattr(subprocess, "run", mock_run)

    is_valid, errors = verify_git_diff(Path("/fake/path"))
    assert is_valid is False
    assert len(errors) > 0


# =====================================================================
# RUN PROCESS INTEGRATION TESTS
# =====================================================================


def test_run_process_returns_false_for_invalid_directory():
    invalid_path = Path("/non/existent/directory/path/here")
    assert run_process(invalid_path) is False


def test_run_process_succeeds_when_git_diff_is_valid(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    script = src_dir / "main.py"
    script.write_text("print('test')", encoding="utf-8")

    # Mock git diff to return a valid comment addition structure
    valid_diff = (
        "diff --git a/src/main.py b/src/main.py\n@@ -0,0 +1 @@\n+# src/main.py\n"
    )
    mock_run = MagicMock(return_value=MagicMock(stdout=valid_diff, returncode=0))
    monkeypatch.setattr(subprocess, "run", mock_run)

    assert run_process(tmp_path) is True
    assert script.read_text(encoding="utf-8") == "# src/main.py\nprint('test')"


def test_run_process_fails_when_git_diff_fails_validation(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    script = src_dir / "main.py"
    script.write_text("print('test')", encoding="utf-8")

    # Mock git diff to simulate an accidental file deletion line change
    invalid_diff = (
        "diff --git a/src/main.py b/src/main.py\n@@ -1,1 +1,0 @@\n-print('test')\n"
    )
    mock_run = MagicMock(return_value=MagicMock(stdout=invalid_diff, returncode=0))
    monkeypatch.setattr(subprocess, "run", mock_run)

    # The process should catch the unsafe git diff and return False
    assert run_process(tmp_path) is False
