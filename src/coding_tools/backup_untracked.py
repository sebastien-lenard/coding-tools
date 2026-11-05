# src/coding_tools/backup_untracked.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Back up untracked files with config file.

Read .git_untracked_to_save in project root. Write to output base dir.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, DirectoryPath

from coding_tools import my_logger

logger = my_logger.logger(__name__)


class UntrackedBackupManager(BaseModel):
    """Back up untracked files based on config file rules.

    Pydantic check. Read .git_untracked_to_save for list. File write access.
    """

    project_path: DirectoryPath
    verbose: bool = False

    _config_name: ClassVar[str] = ".git_untracked_to_save"

    @property
    def config_file_path(self) -> Path:
        """Get path to conf from project root and conf name."""
        return self.project_path / self._config_name

    def execute(self) -> bool:
        """Run backup from conf read to file copies.

        Return True if pass, False on miss conf or IO err. File write access.
        """
        if self.verbose:
            # Verbose setting handled via central config or level if needed
            pass

        logger.start("backup", target=self.project_path, folder=self.project_path)

        if not self.config_file_path.exists():
            logger.error(
                self.project_path,
                f"No conf: {self.config_file_path}",
            )
            return False

        config_data = self._parse_config()
        if not config_data:
            return False

        output_base_dir, items_to_backup = config_data

        if not self._ensure_output_dir(output_base_dir):
            return False

        backup_target_dir = self._get_backup_target_dir(output_base_dir)
        logger.progress(self.project_path, "Start backup", str(backup_target_dir))
        success_count = 0

        for item_str in items_to_backup:
            if self._copy_item(item_str, backup_target_dir):
                success_count += 1

        logger.progress(
            self.project_path,
            "End backup",
            f"Saved {success_count} items",
        )
        logger.end("backup", target=self.project_path)
        return True

    def _ensure_output_dir(self, output_base_dir: Path) -> bool:
        """Check output dir and make if miss.

        Return False on IO err or bad path. File write access.
        """
        if not output_base_dir.exists():
            try:
                output_base_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.exception(
                    self.project_path,
                    "Bad output path",
                )
                return False
        return True

    def _get_backup_target_dir(self, output_base_dir: Path) -> Path:
        """Get date and time stamped folder in output base dir."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return output_base_dir / f"backup_{self.project_path.name}_{timestamp}"

    def _copy_item(self, item_str: str, backup_target_dir: Path) -> bool:
        """Copy file or dir to backup target dir.

        Skip if miss. Return False on IO err or perm err. File write access.
        """
        clean_item_str = item_str.rstrip("/\\")
        source_item = self.project_path / clean_item_str

        if not source_item.exists():
            logger.warning(clean_item_str, "Skipped (Not Found)")
            return False

        destination_path = backup_target_dir / clean_item_str

        try:
            if source_item.is_file():
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_item, destination_path)
                logger.progress(clean_item_str, "Copied")
            elif source_item.is_dir():
                shutil.copytree(
                    source_item,
                    destination_path,
                    dirs_exist_ok=True,
                )
                logger.progress(clean_item_str, "Copied")
        except (PermissionError, shutil.Error):
            logger.exception(
                clean_item_str,
                "Failed copy",
            )
            return False
        else:
            return True

    def _parse_config(self) -> tuple[Path, list[str]] | None:
        """Parse conf file, get base dir and items to backup.

        Return None on read fail or empty file. File read access.
        """
        try:
            content = self.config_file_path.read_text(encoding="utf-8")
            lines = [
                cleaned
                for line in content.splitlines()
                if (cleaned := line.strip()) and not cleaned.startswith("#")
            ]
        except (PermissionError, FileNotFoundError):
            logger.exception(self.project_path, "Failed reading conf")
            return None

        if not lines:
            logger.error(
                self.project_path,
                f"Empty conf: {self.config_file_path}",
            )
            return None

        output_base_dir = Path(lines[0])
        items_to_backup = lines[1:]
        return output_base_dir, items_to_backup


def main() -> None:
    """Parse CLI args, run backup, and exit with status code.

    Commands with options: project_path, -v, --verbose. Default dir is .
    """
    parser = argparse.ArgumentParser(
        description="Back up untracked project files",
    )
    parser.add_argument(
        "project_path",
        type=str,
        nargs="?",
        default=".",
        help="Target dir path (default: current dir)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose",
    )
    args = parser.parse_args()
    my_logger.setup()

    try:
        manager = UntrackedBackupManager(
            project_path=Path(args.project_path),
            verbose=args.verbose,
        )
        success = manager.execute()
    except Exception:
        logger.exception(None, "End due to check breakdown")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
