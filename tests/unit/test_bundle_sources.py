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


@pytest.fixture
def setup_mock_project(tmp_path: Path) -> dict[str, Path]:
    """Set up a mock project structure for testing."""
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


def test_pydantic_enforces_directory_existence_on_init() -> None:
    """Test that Pydantic enforces directory existence during initialization."""
    with pytest.raises(ValidationError):
        SourceBundler(project_path=Path("this/path/does/not/exist/anywhere"))


def test_bundler_executes_successfully_default_output(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test bundler execution success with default output path."""
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
    assert "Start bundle-sources" in caplog.text
    assert "Include optional file" in caplog.text


def test_bundler_executes_successfully_custom_output(
    setup_mock_project: dict[str, Path],
) -> None:
    """Test bundler execution success with a custom output path."""
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
    """Test that the bundler skips missing optional files gracefully."""
    project_dir = tmp_path / "minimal_project"
    project_dir.mkdir()
    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('app')", encoding="utf-8")

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

    assert "Skipped optional file (not found)" in caplog.text


def test_missing_src_folder_logs_error_and_returns_false(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a missing src folder logs an error and returns false."""
    empty_dir = tmp_path / "empty_project"
    empty_dir.mkdir()

    bundler = SourceBundler(project_path=empty_dir, verbose=False)

    with caplog.at_level("ERROR"):
        assert bundler.execute() is False

    assert "Missing src subfolder" in caplog.text


def test_subprocess_called_process_error_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that CalledProcessError from subprocess execution is handled."""
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
    assert "Failed files-to-prompt run" in caplog.text


def test_file_not_found_error_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that FileNotFoundError during subprocess execution is handled."""
    proj = setup_mock_project
    bundler = SourceBundler(project_path=proj["project_dir"])

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        caplog.at_level("ERROR"),
    ):
        assert bundler.execute() is False
    assert "Missing 'uvx' or 'files-to-prompt' commands" in caplog.text


def test_uncreatable_output_directory_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of uncreatable output directories."""
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
    assert "Bad target path" in caplog.text


def test_output_write_os_error_returns_false(
    setup_mock_project: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of OSError during output file writing."""
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
    assert "Failed output writing" in caplog.text


def test_main_gateway_execution_success(
    setup_mock_project: dict[str, Path],
) -> None:
    """Test successful execution via the main CLI gateway."""
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
    """Test failure execution via the main CLI gateway."""
    test_args = ["bundle_sources.py", "non_existent_directory_target"]
    with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_script_execution_entrypoint(
    setup_mock_project: dict[str, Path],
) -> None:
    """Test script execution via direct file runpath execution."""
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
