# tests/unit/test_bundle_sources.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit test suite validating the codebase source bundling workflows."""

import runpy
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from coding_tools import bundle_sources
from coding_tools.bundle_sources import SourceBundler, main

# =====================================================================
# SYSTEM FIXTURES
# =====================================================================


@pytest.fixture
def setup_mock_project(tmp_path: Path) -> dict[str, Path]:
    """Set up a testing environment mimicking structural project paths."""
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()

    src_dir = project_dir / "src"
    src_dir.mkdir()

    core_file = src_dir / "core.py"
    core_file.write_text("print('core')", encoding="utf-8")

    toml_file = project_dir / "pyproject.toml"
    toml_file.write_text('[project]\nname = "test"', encoding="utf-8")

    env_example_file = project_dir / ".env.example"
    env_example_file.write_text("API_KEY=your_key_here", encoding="utf-8")

    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    conftest_file = tests_dir / "conftest.py"
    conftest_file.write_text("import pytest", encoding="utf-8")

    return {
        "project_dir": project_dir,
        "src_dir": src_dir,
        "core_file": core_file,
        "toml_file": toml_file,
        "env_example_file": env_example_file,
        "conftest_file": conftest_file,
    }


# =====================================================================
# STRUCTURAL INITIALIZATION VALIDATION
# =====================================================================


def test_pydantic_enforces_directory_existence_on_init() -> None:
    """Verifies that non-existent directory targets fail Pydantic validation."""
    with pytest.raises(ValidationError):
        SourceBundler(project_path=Path("this/path/does/not/exist/anywhere"))


# =====================================================================
# WORKFLOW EXECUTION FUNCTIONAL TESTS
# =====================================================================


def test_bundler_executes_successfully_default_output(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies standard bundling execution with default output path resolution."""
    proj = setup_mock_project
    bundler = SourceBundler(project_path=proj["project_dir"], verbose=True)

    mock_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="src/core.py\n---\nprint('core')\n",
    )

    with (
        patch("subprocess.run", return_value=mock_completed),
        caplog.at_level("INFO"),
    ):
        assert bundler.execute() is True

    expected_output = proj["project_dir"] / "src_files.txt"
    assert expected_output.exists()
    assert "Target Project Folder" in caplog.text
    assert "Included optional file: pyproject.toml" in caplog.text
    assert "Included optional file: .env.example" in caplog.text
    assert "Included optional file: tests/conftest.py" in caplog.text


def test_bundler_executes_successfully_custom_output(
    setup_mock_project: dict[str, Path],
) -> None:
    """Verifies bundling execution with a custom specified output file."""
    proj = setup_mock_project
    custom_output = proj["project_dir"] / "custom_dir" / "bundle.txt"
    bundler = SourceBundler(
        project_path=proj["project_dir"],
        output_file=custom_output,
        verbose=False,
    )

    mock_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="content\n",
    )

    with patch("subprocess.run", return_value=mock_completed):
        assert bundler.execute() is True

    assert custom_output.exists()


def test_bundler_skips_missing_optional_files(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies optional files are logged as missing and skipped if absent."""
    project_dir = tmp_path / "minimal_project"
    project_dir.mkdir()
    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('app')", encoding="utf-8")

    # Also add an ignored directory with a python file
    # to test the ignore condition branch
    ignored_dir = src_dir / "__pycache__"
    ignored_dir.mkdir()
    (ignored_dir / "cached.py").write_text("print('cached')", encoding="utf-8")

    bundler = SourceBundler(project_path=project_dir, verbose=True)

    mock_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="src/app.py\n---\nprint('app')\n",
    )

    with (
        patch("subprocess.run", return_value=mock_completed),
        caplog.at_level("INFO"),
    ):
        assert bundler.execute() is True

    assert "Optional file not found (skipped): pyproject.toml" in caplog.text
    assert "Optional file not found (skipped): .env.example" in caplog.text
    assert "Optional file not found (skipped): tests/conftest.py" in caplog.text


def test_missing_src_folder_logs_error_and_returns_false(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validates that missing 'src' subfolder aborts execution cleanly."""
    empty_dir = tmp_path / "empty_project"
    empty_dir.mkdir()

    bundler = SourceBundler(project_path=empty_dir, verbose=False)

    with caplog.at_level("ERROR"):
        assert bundler.execute() is False

    assert "Required 'src' subfolder missing at target" in caplog.text


def test_subprocess_called_process_error_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensures subprocess execution failures are caught and logged."""
    proj = setup_mock_project
    bundler = SourceBundler(project_path=proj["project_dir"])

    with (
        patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "files-to-prompt"),
        ),
        caplog.at_level("ERROR"),
    ):
        assert bundler.execute() is False
    assert "Failed executing files-to-prompt subprocess" in caplog.text


def test_file_not_found_error_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validates resilience against missing CLI execution tools (e.g. uvx)."""
    proj = setup_mock_project
    bundler = SourceBundler(project_path=proj["project_dir"])

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        caplog.at_level("ERROR"),
    ):
        assert bundler.execute() is False
    assert "Command 'uvx' or 'files-to-prompt' is not" in caplog.text


def test_uncreatable_output_directory_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensures uncreatable destination folder targets abort safely."""
    proj = setup_mock_project
    custom_output = Path("/uncreatable_root_dir_xyz/bundle.txt")
    bundler = SourceBundler(
        project_path=proj["project_dir"],
        output_file=custom_output,
    )

    with (
        patch.object(Path, "mkdir", side_effect=PermissionError),
        caplog.at_level("ERROR"),
    ):
        assert bundler.execute() is False
    assert "Output base destination path is invalid or uncreatable" in caplog.text


def test_output_write_os_error_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guarantees graceful failure handling when writing the bundle file fails."""
    proj = setup_mock_project
    bundler = SourceBundler(project_path=proj["project_dir"])

    mock_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="src/core.py\n---\nprint('core')\n",
    )

    with (
        patch("subprocess.run", return_value=mock_completed),
        patch.object(Path, "write_text", side_effect=OSError),
        caplog.at_level("ERROR"),
    ):
        assert bundler.execute() is False
    assert "Failed to write bundled output to" in caplog.text


def test_main_gateway_execution_success(
    setup_mock_project: dict[str, Path],
) -> None:
    """Verifies that the CLI gateway entry point terminates correctly on success."""
    proj = setup_mock_project
    test_args = ["bundle_sources.py", str(proj["project_dir"]), "-v"]

    mock_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="src/core.py\n---\nprint('core')\n",
    )

    with (
        patch("subprocess.run", return_value=mock_completed),
        patch("sys.argv", test_args),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0


def test_main_gateway_execution_failure() -> None:
    """Verifies that the CLI gateway flags systemic errors with status exit code 1."""
    test_args = ["bundle_sources.py", "non_existent_directory_target"]
    with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_script_execution_entrypoint(
    setup_mock_project: dict[str, Path],
) -> None:
    """Asserts execution coverage over the primary standard file entrypoint block.

    Uses runpy to safely invoke the module execution path directly without subprocesses.
    """
    proj = setup_mock_project
    target_file_path = str(Path(bundle_sources.__file__).resolve())
    test_args = ["bundle_sources.py", str(proj["project_dir"])]

    mock_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="src/core.py\n---\nprint('core')\n",
    )

    with (
        patch("subprocess.run", return_value=mock_completed),
        patch("sys.argv", test_args),
        pytest.raises(SystemExit) as exc_info,
    ):
        runpy.run_path(target_file_path, run_name="__main__")
    assert exc_info.value.code == 0
