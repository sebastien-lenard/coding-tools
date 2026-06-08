"""Tests for the workspace layout and compliance metadata verification engine."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from coding_tools.workspace_stamper import (
    FILE_LICENSE,
    FILE_NOTICE,
    TargetWorkspace,
    WorkspaceStamper,
    main,
)


def create_compliance_environment(
    root: Path,
    has_license: bool = True,
    has_notice: bool = True,
) -> tuple[Path, Path]:
    """Stage structural compliance environments with standard formats."""
    lic = root / FILE_LICENSE
    notc = root / FILE_NOTICE
    if has_license:
        lic.write_text("Apache License Version 2.0\nLine 2 info", encoding="utf-8")
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
    file_not_py = src / "README.md"
    file_ok.touch()
    file_bad.touch()
    file_not_py.touch()

    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    resolved = ws.resolve_files()

    assert file_ok in resolved
    assert file_bad not in resolved
    assert file_not_py not in resolved


def test_workspace_file_resolution_single_file(tmp_path: Path) -> None:
    """Verifies that resolving a single file path behaves deterministically."""
    file_ok = tmp_path / "app.py"
    file_ok.touch()
    ws = TargetWorkspace(project_dir=tmp_path, target_path=file_ok)
    assert ws.resolve_files() == [file_ok]

    file_bad = tmp_path / "app.txt"
    file_bad.touch()
    ws_bad = TargetWorkspace(project_dir=tmp_path, target_path=file_bad)
    assert ws_bad.resolve_files() == []


# =====================================================================
# INFRASTRUCTURE & METADATA TESTS WITH NEW RESILIENT SPECS
# =====================================================================


def test_missing_license_triggers_warning_but_stamps_successfully(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warns if LICENSE is missing, but still injects SPDX-License-Identifier."""
    create_compliance_environment(tmp_path, has_license=False, has_notice=True)
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)

    with caplog.at_level("WARNING"):
        engine._evaluate_legal_infrastructure()

    assert ws.run_license_stamp
    assert "is missing from project root" in caplog.text


def test_missing_notice_triggers_warning_but_stamps_rest(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warns if NOTICE is missing, skipping copyright but stamping license-id."""
    create_compliance_environment(tmp_path, has_license=True, has_notice=False)
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        extracted_license_id="MIT",
    )
    engine = WorkspaceStamper(workspace=ws)

    with caplog.at_level("WARNING"):
        engine._evaluate_legal_infrastructure()

    assert ws.run_license_stamp
    assert ws.extracted_copyright is None
    assert "is missing from project root" in caplog.text


def test_unparseable_license_captured_and_logged(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Captures and logs the header elements cleanly from valid LICENSE."""
    create_compliance_environment(tmp_path)
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)

    with caplog.at_level("INFO"):
        engine._evaluate_legal_infrastructure()

    assert "LICENSE headers detected:" in caplog.text


# =====================================================================
# CONTENT TRANSFORMATION & FEATURE-FLAG TESTS
# =====================================================================


def test_generates_both_path_and_license_on_empty_file(tmp_path: Path) -> None:
    """Inserts stacked structural modifications cleanly inside empty source targets."""
    create_compliance_environment(tmp_path)
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)
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
    """Applies only path elements when license stamping flags are dropped."""
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        run_license_stamp=False,
    )
    engine = WorkspaceStamper(workspace=ws)

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
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)
    engine._evaluate_legal_infrastructure()

    target_file = tmp_path / "main.py"
    content, modified = engine._generate_updated_content(target_file, "print('ok')")

    assert modified
    assert "# main.py\n" not in content
    assert "# SPDX-License-Identifier: Apache-2.0\n" in content


def test_preserves_interpreter_directives(tmp_path: Path) -> None:
    """Ensures paths and license definitions append below shebang blocks correctly."""
    create_compliance_environment(tmp_path)
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)
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
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)
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


def test_purges_legacy_tags_when_license_disabled(tmp_path: Path) -> None:
    """Cleans up and removes legacy tags if license checking is turned off."""
    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=tmp_path,
        run_license_stamp=False,
    )
    engine = WorkspaceStamper(workspace=ws)

    dirty_input = "# main.py\n# SPDX-FileCopyrightText: Legacy\nprint('run')"
    target_file = tmp_path / "main.py"
    content, modified = engine._generate_updated_content(target_file, dirty_input)

    assert modified
    assert "Legacy" not in content
    assert "main.py" in content


# =====================================================================
# INTEGRATION & FAULT-TOLERANCE TESTS
# =====================================================================


def test_engine_run_completes_end_to_end_successfully(tmp_path: Path) -> None:
    """Verifies execution transaction cycles for verified structures."""
    create_compliance_environment(tmp_path)
    script = tmp_path / "main.py"
    script.write_text("pass", encoding="utf-8")

    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=script,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)

    assert engine.run()
    updated_content = script.read_text(encoding="utf-8")
    assert "# main.py\n" in updated_content
    assert "SPDX-License-Identifier: Apache-2.0" in updated_content


def test_engine_blocked_by_permission_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies logging safety if target paths cannot be decoded or read."""
    create_compliance_environment(tmp_path)
    script = tmp_path / "main.py"
    script.write_text("print('test')", encoding="utf-8")

    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=script,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)

    # Force encoding mismatch issues
    script.write_bytes(b"\x80\x81\xff")

    with caplog.at_level("WARNING"):
        assert engine.run()
    assert "I/O execution blocked for" in caplog.text


def test_process_file_failure_captured_gracefully(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensures file modification write errors are captured and logged."""
    ws = TargetWorkspace(project_dir=tmp_path, target_path=tmp_path)
    engine = WorkspaceStamper(workspace=ws)

    with caplog.at_level("ERROR"):
        status = engine._process_file(tmp_path, "content")

    assert not status
    assert "Failed execution lifecycle on target" in caplog.text


def test_safety_engine_catches_unauthorized_functional_mutations(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fails and alerts when structural changes alter functional logic."""
    create_compliance_environment(tmp_path)
    script = tmp_path / "main.py"
    script.write_text("print('safe')", encoding="utf-8")

    ws = TargetWorkspace(
        project_dir=tmp_path,
        target_path=script,
        extracted_license_id="Apache-2.0",
    )
    engine = WorkspaceStamper(workspace=ws)

    baselines = {script: script.read_text(encoding="utf-8")}
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


# =====================================================================
# NEW COMPLEMENTARY SPECIFICATIONS CLI TESTS
# =====================================================================


def test_cli_requires_license_id_unless_no_license(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validates that execution terminates if --license-id is missing."""
    script = tmp_path / "main.py"
    script.touch()

    monkeypatch.setattr(
        sys,
        "argv",
        ["workspace_stamper", str(script), "--project-dir", str(tmp_path)],
    )

    with pytest.raises(SystemExit) as sysexit:
        main()

    assert sysexit.value.code == 1


def test_cli_invalid_license_id_pattern(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checks character verification for invalid licensing patterns."""
    script = tmp_path / "main.py"
    script.touch()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workspace_stamper",
            str(script),
            "--project-dir",
            str(tmp_path),
            "--license-id",
            "Apache 2.0!",
        ],
    )

    with pytest.raises(SystemExit) as sysexit:
        main()

    assert sysexit.value.code == 1


def test_cli_mutual_deactivation_termination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Asserts clean termination with logging when stamps are turned off."""
    script = tmp_path / "main.py"
    script.touch()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workspace_stamper",
            str(script),
            "--no-path",
            "--no-license",
        ],
    )

    with caplog.at_level("INFO"), pytest.raises(SystemExit) as sysexit:
        main()

    assert sysexit.value.code == 0
    assert "No stamping will be carried out" in caplog.text


def test_cli_optional_project_dir_when_target_is_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default directory paths are inferred cleanly from targets."""
    create_compliance_environment(tmp_path)
    script = tmp_path / "main.py"
    script.write_text("pass", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workspace_stamper",
            str(tmp_path),
            "-l",
            "MIT",
        ],
    )

    with pytest.raises(SystemExit) as sysexit:
        main()

    assert sysexit.value.code == 0


def test_cli_raises_error_if_project_dir_missing_on_file_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aborts execution if file path targets lack project directory parameters."""
    script = tmp_path / "main.py"
    script.touch()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workspace_stamper",
            str(script),
            "-l",
            "MIT",
        ],
    )

    with pytest.raises(SystemExit) as sysexit:
        main()

    assert sysexit.value.code == 1
