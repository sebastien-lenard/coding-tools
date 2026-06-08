from pathlib import Path

import pytest
from pydantic import ValidationError

from src.coding_tools.workspace_stamper import (
    FILE_LICENSE,
    FILE_NOTICE,
    CodeStamperEngine,
    TargetWorkspace,
)


def create_compliance_environment(
    root: Path,
    has_license: bool = True,
    has_notice: bool = True,
) -> tuple[Path, Path]:
    """Stage structural compliance environments."""
    lic = root / FILE_LICENSE
    notc = root / FILE_NOTICE
    if has_license:
        lic.write_text("Apache License\nVersion 2.0", encoding="utf-8")
    if has_notice:
        notc.write_text(
            "Copyright 2026 Sebastien Lenard <sebastien.lenard@gmail.com>",
            encoding="utf-8",
        )
    return lic, notc


# =====================================================================
# INITIALIZATION & VALIDATION TESTS
# =====================================================================


def test_pydantic_validation_fails_for_invalid_directory() -> None:
    """Verifies that non-existent workspace targets fail structural tracking."""
    with pytest.raises(ValidationError):
        TargetWorkspace(
            project_dir=Path("/non/existent/dir"),
            target_path=Path("/non/existent/dir"),
        )


def test_workspace_file_resolution_ignores_environments(tmp_path: Path) -> None:
    """Verifies file discovery handles recursive filters and ignores environments."""
    src = tmp_path / "src"
    venv = tmp_path / ".venv"
    src.mkdir()
    venv.mkdir()

    file_ok = src / "app.py"
    file_bad = venv / "lib.py"
    file_ok.touch()
    file_bad.touch()

    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    resolved = ws.resolve_files()

    assert file_ok in resolved
    assert file_bad not in resolved


# =====================================================================
# LEGAL INFRASTRUCTURE & METADATA TESTS
# =====================================================================


def test_missing_infrastructure_triggers_warning_and_deactivates(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Deactivates licensing gracefully if infrastructure dependencies are missing."""
    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    engine = CodeStamperEngine(workspace=ws)

    with caplog.at_level("WARNING"):
        engine._evaluate_legal_infrastructure()

    assert not ws.run_license_stamp
    assert "missing at project root" in caplog.text


def test_unrecognized_license_signature_deactivates_stamping(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Short-circuits legal updates if the LICENSE string matches no signatures."""
    create_compliance_environment(tmp_path, has_notice=True)
    (tmp_path / FILE_LICENSE).write_text("Unknown Custom License", encoding="utf-8")

    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    engine = CodeStamperEngine(workspace=ws)

    with caplog.at_level("WARNING"):
        engine._evaluate_legal_infrastructure()

    assert not ws.run_license_stamp
    assert "Unrecognized signature inside LICENSE" in caplog.text


def test_missing_notice_copyright_deactivates_stamping(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Deactivates licensing updates if NOTICE is present but has no copyright."""
    create_compliance_environment(tmp_path, has_notice=False)
    (tmp_path / FILE_NOTICE).write_text("Just generic text", encoding="utf-8")

    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    engine = CodeStamperEngine(workspace=ws)

    with caplog.at_level("WARNING"):
        engine._evaluate_legal_infrastructure()

    assert not ws.run_license_stamp
    assert "Could not locate a valid 'Copyright' string" in caplog.text


# =====================================================================
# CONTENT TRANSFORMATION & FEATURE-FLAG TESTS
# =====================================================================


def test_generates_both_path_and_license_on_empty_file(tmp_path: Path) -> None:
    """Inserts stacked structural modifications cleanly inside empty source targets."""
    create_compliance_environment(tmp_path)
    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    engine = CodeStamperEngine(workspace=ws)
    engine._evaluate_legal_infrastructure()

    target_file = tmp_path / "main.py"
    content, modified = engine._generate_updated_content(target_file, "")

    assert modified
    expected = (
        "# main.py\n"
        "# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com>\n"
        "# SPDX-License-Identifier: Apache-2.0\n"
    )
    assert content == expected


def test_only_path_stamped_when_license_disabled(tmp_path: Path) -> None:
    """Applies only path elements when license stamping flags are explicitly dropped."""
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        run_license_stamp=False,
    )
    engine = CodeStamperEngine(workspace=ws)

    target_file = tmp_path / "main.py"
    content, modified = engine._generate_updated_content(target_file, "print('ok')")

    assert modified
    assert "# main.py\nprint('ok')" in content
    assert "SPDX-License-Identifier" not in content


def test_only_license_stamped_when_path_disabled(tmp_path: Path) -> None:
    """Applies only license lines if path elements are deactivated."""
    create_compliance_environment(tmp_path)
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        run_path_stamp=False,
    )
    engine = CodeStamperEngine(workspace=ws)
    engine._evaluate_legal_infrastructure()

    target_file = tmp_path / "main.py"
    content, modified = engine._generate_updated_content(target_file, "print('ok')")

    assert modified
    assert "# main.py\n" not in content
    assert "# SPDX-License-Identifier: Apache-2.0\n" in content


def test_preserves_interpreter_directives(tmp_path: Path) -> None:
    """Ensures paths and license definitions append below shebang blocks correctly."""
    create_compliance_environment(tmp_path)
    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    engine = CodeStamperEngine(workspace=ws)
    engine._evaluate_legal_infrastructure()

    original = "#!/usr/bin/env python3\n# coding: utf-8\nprint('code')"
    target_file = tmp_path / "main.py"
    content, modified = engine._generate_updated_content(target_file, original)

    assert modified
    lines = content.splitlines()
    assert lines[0] == "#!/usr/bin/env python3"
    assert lines[1] == "# coding: utf-8"
    assert lines[2] == "# main.py"


def test_overwrites_legacy_and_dirty_spdx_lines(tmp_path: Path) -> None:
    """Slices out broken or legacy license tags to keep structural layout clean."""
    create_compliance_environment(tmp_path)
    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    engine = CodeStamperEngine(workspace=ws)
    engine._evaluate_legal_infrastructure()

    dirty_input = (
        "# main.py\n"
        "# SPDX-FileCopyrightText: Outdated Holder 2020\n"
        "# SPDX-License-Identifier: MIT\n"
        "print('run')"
    )
    target_file = tmp_path / "main.py"
    content, modified = engine._generate_updated_content(target_file, dirty_input)

    assert modified
    assert "Outdated Holder" not in content
    assert "MIT" not in content
    assert "Apache-2.0" in content


# =====================================================================
# INTEGRATION & SAFETY TESTS
# =====================================================================


def test_engine_run_completes_end_to_end_successfully(tmp_path: Path) -> None:
    """Verifies flawless execution transaction cycles for verified structures."""
    create_compliance_environment(tmp_path)
    script = tmp_path / "main.py"
    script.write_text("pass", encoding="utf-8")

    ws = TargetWorkspace(project_dir=tmp_path, target_path=script)
    engine = CodeStamperEngine(workspace=ws)

    assert engine.run()
    updated_content = script.read_text(encoding="utf-8")
    assert "# main.py\n" in updated_content
    assert "SPDX-License-Identifier: Apache-2.0" in updated_content


def test_safety_engine_catches_unauthorized_functional_mutations(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fails and alerts when structural changes alter functional logic."""
    create_compliance_environment(tmp_path)
    script = tmp_path / "main.py"
    script.write_text("print('safe')", encoding="utf-8")

    ws = TargetWorkspace(project_dir=tmp_path, target_path=script)
    engine = CodeStamperEngine(workspace=ws)

    # Cache original state
    baselines = {script: script.read_text(encoding="utf-8")}

    # Update file correctly
    engine._process_file(script, baselines[script])

    # Simulate adversarial file mutation (code tampering post-processing)
    script.write_text(
        "# main.py\n"
        "# SPDX-FileCopyrightText: 2026 Sebastien Lenard\n"
        "# SPDX-License-Identifier: Apache-2.0\n"
        "print('malicious injection')",
        encoding="utf-8",
    )

    with caplog.at_level("CRITICAL"):
        status = engine._verify_modifications(baselines)

    assert not status
    assert "SAFETY ENGINE ALERT" in caplog.text
