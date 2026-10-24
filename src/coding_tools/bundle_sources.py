# src/coding_tools/bundle_sources.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Bundle project source files into text file and strip redundant headers."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, DirectoryPath

from coding_tools.logger import get_project_logger, setup_logging

# Force Python into UTF-8 mode on Windows
os.environ["PYTHONUTF8"] = "1"

logger = get_project_logger(__name__)


class SourceBundler(BaseModel):
    """Bundle project source files into text document via Pydantic validation.

    Uses files-to-prompt via uvx. Skips missing optional files. Needs internet/uvx.
    """

    project_path: DirectoryPath
    output_file: Path | None = None
    verbose: bool = False

    _default_output_name: ClassVar[str] = "src_files.txt"
    # Define allowed source file extensions in the src directory
    _allowed_extensions: ClassVar[set[str]] = {".py", ".pyx", ".pxd", ".pyi"}

    @property
    def target_output_path(self) -> Path:
        """Get output file path."""
        if self.output_file:
            return self.output_file
        return self.project_path / self._default_output_name

    @property
    def src_path(self) -> Path:
        """Get expected src subfolder path."""
        return self.project_path / "src"

    def execute(self) -> bool:
        """Read source files and write bundled output.

        False if src folder missing, subprocess fail, or write error.
        """
        logger.start(
            "bundle-sources",
            target=self.project_path,
            folder=self.project_path,
        )

        if not self.src_path.exists() or not self.src_path.is_dir():
            logger.error(
                self.src_path,
                f"Required src subfolder missing: {self.src_path}",
            )
            return False

        output_path = self.target_output_path
        if not self._ensure_output_dir(output_path.parent):
            return False

        try:
            combined_content = self._run_files_to_prompt()
        except subprocess.CalledProcessError:
            logger.exception(None, "Failed executing files-to-prompt subprocess")
            return False
        except FileNotFoundError:
            logger.exception(
                None,
                "Command 'uvx' or 'files-to-prompt' not installed / available in PATH.",
            )
            return False

        try:
            output_path.write_text(combined_content, encoding="utf-8")
        except OSError:
            logger.exception(output_path, "Failed to write bundled output")
            return False

        logger.progress(output_path, "Bundled code", f"to {output_path.name}")
        logger.end("bundle-sources", target=self.project_path)
        return True

    def _ensure_output_dir(self, output_base_dir: Path) -> bool:
        """Check output destination directory accessibility."""
        if not output_base_dir.exists():
            try:
                output_base_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.exception(
                    output_base_dir,
                    "Destination path invalid or uncreatable",
                )
                return False
        return True

    def _run_files_to_prompt(self) -> str:
        """Run files-to-prompt on filtered source files and optional project files."""
        accumulated_output = ""

        # Gather files matching allowed extensions, ignoring junk directories
        ignore_dirs = {"__pycache__", ".git", "venv"}
        source_files = []

        for path in self.src_path.rglob("*"):
            if any(part in ignore_dirs for part in path.parts):
                continue
            if path.is_file() and path.suffix in self._allowed_extensions:
                source_files.append(path)

        # Sort for deterministic output ordering
        source_files.sort()

        if source_files:
            cmd_src = [
                "uvx",
                "files-to-prompt",
                *[str(p) for p in source_files],
            ]
            logger.progress(None, "Scan source files", f"count={len(source_files)}")
            result_src = subprocess.run(  # noqa: S603
                cmd_src,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            accumulated_output += result_src.stdout

        # Conditionally scan specific target files if they exist
        optional_files = [
            "pyproject.toml",
            ".env.example",
            "tests/conftest.py",
        ]

        for file_rel_path in optional_files:
            target_file = self.project_path / file_rel_path
            if target_file.exists() and target_file.is_file():
                logger.progress(file_rel_path, "Include optional file")
                cmd_file = [
                    "uvx",
                    "files-to-prompt",
                    str(target_file),
                ]
                result_file = subprocess.run(  # noqa: S603
                    cmd_file,
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding="utf-8",
                )
                accumulated_output += result_file.stdout
            else:
                logger.progress(file_rel_path, "Optional file skipped (not found)")

        return accumulated_output


def main() -> None:
    """Run CLI to parse arguments and run SourceBundler."""
    parser = argparse.ArgumentParser(
        description=(
            "Bundle project source files into a single text file, "
            "stripping redundant headers."
        ),
    )
    parser.add_argument(
        "project_path",
        type=str,
        nargs="?",
        default=".",
        help=("Path to the target project directory (default: current directory)"),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help=(
            "Destination text file path "
            "(default: 'src_files.txt' at the root of the project)"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase output verbosity.",
    )
    args = parser.parse_args()

    setup_logging()

    try:
        bundler = SourceBundler(
            project_path=Path(args.project_path),
            output_file=Path(args.output) if args.output else None,
            verbose=args.verbose,
        )
        success = bundler.execute()
    except Exception:
        logger.exception(None, "Terminated due to validation breakdown")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
