# src/coding_tools/backup_untracked.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Automates backups of untracked project resources."""

import argparse
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, DirectoryPath

logger = logging.getLogger("coding_tools.backup_untracked")


class UntrackedBackupManager(BaseModel):
    """Automate backups of local untracked files based on project configurations.

    Uses Pydantic validation to protect file-system execution targets.
    """

    project_path: DirectoryPath
    verbose: bool = False

    _config_name: ClassVar[str] = ".git_untracked_to_save"

    @property
    def config_file_path(self) -> Path:
        """Returns the calculated configuration path."""
        return self.project_path / self._config_name

    def execute(self) -> bool:
        """Orchestrates reading the configurations and backing up files.

        Returns True if successful, False otherwise.
        """
        if self.verbose:
            logger.setLevel(logging.INFO)

        logger.info("Target Project Folder: %s", self.project_path)

        if not self.config_file_path.exists():
            logger.error(
                "Configuration file missing at target: %s",
                self.config_file_path,
            )
            return False

        config_data = self._parse_config()
        if not config_data:
            return False

        output_base_dir, items_to_backup = config_data

        if not self._ensure_output_dir(output_base_dir):
            return False

        backup_target_dir = self._get_backup_target_dir(output_base_dir)
        logger.info("Initializing dynamic backup into: %s", backup_target_dir)
        success_count = 0

        for item_str in items_to_backup:
            if self._copy_item(item_str, backup_target_dir):
                success_count += 1

        logger.info(
            "Backup finished. Successfully saved %s items.",
            success_count,
        )
        return True

    def _ensure_output_dir(self, output_base_dir: Path) -> bool:
        """Verify output destination directory is accessible or buildable."""
        if not output_base_dir.exists():
            try:
                output_base_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.exception(
                    "Backup base destination path is invalid or uncreatable",
                )
                return False
        return True

    def _get_backup_target_dir(self, output_base_dir: Path) -> Path:
        """Generate a unique timestamped destination target folder."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return output_base_dir / f"backup_{self.project_path.name}_{timestamp}"

    def _copy_item(self, item_str: str, backup_target_dir: Path) -> bool:
        """Normalize and copy a single source item string to the destination."""
        clean_item_str = item_str.rstrip("/\\")
        source_item = self.project_path / clean_item_str

        if not source_item.exists():
            logger.warning("Skipped (Not Found): %s", clean_item_str)
            return False

        destination_path = backup_target_dir / clean_item_str

        try:
            if source_item.is_file():
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_item, destination_path)
                logger.info("📄 Copied File: %s", clean_item_str)
            elif source_item.is_dir():
                shutil.copytree(
                    source_item,
                    destination_path,
                    dirs_exist_ok=True,
                )
                logger.info("📁 Copied Folder: %s/", clean_item_str)
        except (PermissionError, shutil.Error):
            logger.exception(
                "IO Failure tracking copy targets for %s",
                clean_item_str,
            )
            return False
        else:
            return True

    def _parse_config(self) -> tuple[Path, list[str]] | None:
        """Parse lines within the backup schema configuration file."""
        try:
            content = self.config_file_path.read_text(encoding="utf-8")
            lines = [
                cleaned
                for line in content.splitlines()
                if (cleaned := line.strip()) and not cleaned.startswith("#")
            ]
        except (PermissionError, FileNotFoundError):
            logger.exception("Failed to securely read configuration file")
            return None

        if not lines:
            logger.error(
                "Configuration file at %s is completely empty.",
                self.config_file_path,
            )
            return None

        # Resolve paths dynamically to handle real environment contexts smoothly
        output_base_dir = Path(lines[0])
        items_to_backup = lines[1:]
        return output_base_dir, items_to_backup


def main() -> None:
    """CLI Gateway transforming raw arguments into verified Pydantic contexts."""
    parser = argparse.ArgumentParser(
        description="Safely back up untracked local files.",
    )
    parser.add_argument(
        "project_path",
        type=str,
        nargs="?",
        default=".",
        help="Path to the target project directory (default: current directory)",
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
        manager = UntrackedBackupManager(
            project_path=Path(args.project_path),
            verbose=args.verbose,
        )
        success = manager.execute()
    except Exception:
        logger.exception("Execution terminated due to validation breakdown")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
