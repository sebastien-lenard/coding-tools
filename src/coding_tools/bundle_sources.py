# bundle_sources.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Bundle project source files into a single text file, stripping redundant headers."""

import argparse
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, DirectoryPath

# Force Python into UTF-8 mode on Windows
os.environ["PYTHONUTF8"] = "1"

logger = logging.getLogger("coding_tools.bundle_sources")


class SourceBundler(BaseModel):
    """Automates bundling of project source files into a single text document.

    Uses Pydantic validation to protect file-system execution targets.
    """

    project_path: DirectoryPath
    output_file: Path | None = None
    verbose: bool = False

    _default_output_name: ClassVar[str] = "src_files.txt"

    @property
    def target_output_path(self) -> Path:
        """Returns the calculated output file path."""
        if self.output_file:
            return self.output_file
        return self.project_path / self._default_output_name

    @property
    def src_path(self) -> Path:
        """Returns the expected 'src' subfolder path."""
        return self.project_path / "src"

    def execute(self) -> bool:
        """Orchestrates reading source files and writing the bundled output.

        Returns True if successful, False otherwise.
        """
        if self.verbose:
            logger.setLevel(logging.INFO)

        logger.info("Target Project Folder: %s", self.project_path)

        if not self.src_path.exists() or not self.src_path.is_dir():
            logger.error(
                "Required 'src' subfolder missing at target: %s",
                self.src_path,
            )
            return False

        output_path = self.target_output_path
        if not self._ensure_output_dir(output_path.parent):
            return False

        try:
            combined_content = self._run_files_to_prompt()
        except subprocess.CalledProcessError:
            logger.exception("Failed executing files-to-prompt subprocess")
            return False
        except FileNotFoundError:
            logger.exception(
                "Command 'uvx' or 'files-to-prompt' is not "
                "installed or available in PATH.",
            )
            return False

        # Matches the filepath line and the '---' line at the start of each block
        pattern = r"^[^\r\n]+\r?\n---\r?\n"
        cleaned_content = re.sub(
            pattern,
            "",
            combined_content,
            flags=re.MULTILINE,
        )

        try:
            output_path.write_text(cleaned_content, encoding="utf-8")
        except OSError:
            logger.exception(
                "Failed to write bundled output to: %s",
                output_path,
            )
            return False

        logger.info("Codebase successfully bundled into: %s", output_path)
        return True

    def _ensure_output_dir(self, output_base_dir: Path) -> bool:
        """Verify output destination directory is accessible or buildable."""
        if not output_base_dir.exists():
            try:
                output_base_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.exception(
                    "Output base destination path is invalid or uncreatable",
                )
                return False
        return True

    def _run_files_to_prompt(self) -> str:
        """Execute files-to-prompt commands against the project structure."""
        # Scan inside the project's src directory
        cmd1 = [
            "uvx",
            "files-to-prompt",
            str(self.src_path),
            "--ignore",
            "__pycache__",
            "--ignore",
            ".git",
            "--ignore",
            "venv",
        ]
        logger.info("Running command: %s", " ".join(cmd1))
        result1 = subprocess.run(  # noqa: S603
            cmd1,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )

        # Scan root configuration files (like pyproject.toml) within the project path
        cmd2 = [
            "uvx",
            "files-to-prompt",
            str(self.project_path),
            "--include-hidden",
            "-e",
            "example",
            "-e",
            "toml",
        ]
        logger.info("Running command: %s", " ".join(cmd2))
        result2 = subprocess.run(  # noqa: S603
            cmd2,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )

        return result1.stdout + result2.stdout


def main() -> None:
    """CLI Gateway transforming raw arguments into verified Pydantic contexts."""
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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        bundler = SourceBundler(
            project_path=Path(args.project_path),
            output_file=Path(args.output) if args.output else None,
            verbose=args.verbose,
        )
        success = bundler.execute()
    except Exception:
        logger.exception("Execution terminated due to validation breakdown")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
