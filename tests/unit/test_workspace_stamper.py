from pathlib import Path

import pytest
from pydantic import ValidationError

from src.coding_tools.workspace_stamper import PathStamper

# =====================================================================
# INITIALIZATION & VALIDATION TESTS
# =====================================================================


def test_pydantic_validation_fails_for_invalid_directory():
    with pytest.raises(ValidationError):
        PathStamper(project_dir=Path("/non/existent/directory/path/here"))


def test_pydantic_validation_passes_for_valid_directory(tmp_path):
    stamper = PathStamper(project_dir=tmp_path)
    assert stamper.project_dir == tmp_path


# =====================================================================
# FUNCTIONAL LOGIC TESTS
# =====================================================================


def test_adds_path_comment_to_empty_file(tmp_path):
    stamper = PathStamper(project_dir=tmp_path)
    new_content, modified = stamper._generate_updated_content("", "src/utils/config.py")
    assert modified is True
    assert new_content == "# src/utils/config.py\n"


def test_preserves_shebang_and_coding_header_and_prepends_path(tmp_path):
    stamper = PathStamper(project_dir=tmp_path)
    content = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nprint('Hello World')\n"
    new_content, modified = stamper._generate_updated_content(
        content, "src/utils/config.py"
    )

    assert modified is True
    expected = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# src/utils/config.py\n"
        "print('Hello World')\n"
    )
    assert new_content == expected


def test_no_modification_if_correct_path_exists(tmp_path):
    stamper = PathStamper(project_dir=tmp_path)
    content = "#!/usr/bin/env python3\n# src/utils/config.py\nprint('Code')\n"
    new_content, modified = stamper._generate_updated_content(
        content, "src/utils/config.py"
    )
    assert modified is False
    assert new_content == content


def test_scans_deep_folders_and_ignores_venvs(tmp_path):
    src_dir = tmp_path / "src" / "utils"
    venv_dir = tmp_path / ".venv" / "lib"
    src_dir.mkdir(parents=True)
    venv_dir.mkdir(parents=True)

    file1 = tmp_path / "src" / "main.py"
    file2 = tmp_path / "src" / "utils" / "config.py"
    ignored_venv = tmp_path / ".venv" / "lib" / "site.py"

    for f in [file1, file2, ignored_venv]:
        f.touch()

    stamper = PathStamper(project_dir=tmp_path)
    found_files = stamper._scan_files()

    assert file1 in found_files
    assert file2 in found_files
    assert ignored_venv not in found_files
    assert len(found_files) == 2


# =====================================================================
# END-TO-END INTEGRATION & SAFETY SAFETY TESTS
# =====================================================================


def test_path_stamper_succeeds_on_valid_execution(tmp_path):
    script = tmp_path / "main.py"
    script.write_text("print('test')", encoding="utf-8")

    stamper = PathStamper(project_dir=tmp_path)
    assert stamper.run() is True
    assert script.read_text(encoding="utf-8") == "# main.py\nprint('test')"


def test_path_stamper_fails_when_non_header_code_changes_occur(tmp_path, caplog):
    script = tmp_path / "main.py"
    script.write_text("print('original')", encoding="utf-8")

    stamper = PathStamper(project_dir=tmp_path)

    # We simulate an adversarial environment where code is structurally deleted
    # alongside running the stamper step
    def suspicious_activity_run():
        py_files = stamper._scan_files()
        baselines = {f: f.read_text(encoding="utf-8") for f in py_files}

        # Stamper updates the header
        stamper._stamp_file(script, baselines[script])

        # Unexpected side-effect change occurs: original code gets tampered with
        script.write_text("# main.py\nprint('malicious injection')", encoding="utf-8")

        return stamper._verify_modifications(baselines)

    with caplog.at_level("ERROR"):
        execution_status = suspicious_activity_run()
        assert execution_status is False

    assert "CRITICAL ERROR: SAFETY VALIDATION FAILED!" in caplog.text
