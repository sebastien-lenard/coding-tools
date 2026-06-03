import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, DirectoryPath

logger = logging.getLogger("coding_tools.backup_untracked")


class UntrackedBackupManager(BaseModel):
    """
    Automates backups of local untracked files based on project configurations.
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
        """
        Orchestrates reading the configurations and backing up files.
        Returns True if successful, False otherwise.
        """
        if self.verbose:
            logger.setLevel(logging.INFO)

        logger.info(f"Target Project Folder: {self.project_path}")

        if not self.config_file_path.exists():
            logger.error(
                f"Configuration file missing at target: {self.config_file_path}"
            )
            return False

        config_data = self._parse_config()
        if not config_data:
            return False

        output_base_dir, items_to_backup = config_data

        # Verify output destination target directory is accessible or buildable
        if not output_base_dir.exists():
            try:
                output_base_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(
                    f"Backup base destination path is invalid or uncreatable: {e}"
                )
                return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_target_dir = (
            output_base_dir / f"backup_{self.project_path.name}_{timestamp}"
        )

        logger.info(f"Initializing dynamic backup into: {backup_target_dir}")
        success_count = 0

        for item_str in items_to_backup:
            # Normalize target names to handle accidental trailing slashes cleanly
            clean_item_str = item_str.rstrip("/\\")
            source_item = self.project_path / clean_item_str

            if not source_item.exists():
                logger.warning(f"Skipped (Not Found): {clean_item_str}")
                continue

            destination_path = backup_target_dir / clean_item_str

            try:
                if source_item.is_file():
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_item, destination_path)
                    logger.info(f"📄 Copied File: {clean_item_str}")
                    success_count += 1
                elif source_item.is_dir():
                    shutil.copytree(source_item, destination_path, dirs_exist_ok=True)
                    logger.info(f"📁 Copied Folder: {clean_item_str}/")
                    success_count += 1
            except (PermissionError, shutil.Error) as e:
                logger.error(
                    f"IO Failure tracking copy targets for {clean_item_str}: {e}"
                )

        logger.info(f"Backup finished. Successfully saved {success_count} items.")
        return True

    def _parse_config(self) -> tuple[Path, list[str]] | None:
        """Parses lines within the backup schema configuration file."""
        try:
            content = self.config_file_path.read_text(encoding="utf-8")
            lines = [
                cleaned
                for line in content.splitlines()
                if (cleaned := line.strip()) and not cleaned.startswith("#")
            ]
        except (PermissionError, FileNotFoundError) as e:
            logger.error(f"Failed to securely read configuration file: {e}")
            return None

        if not lines:
            logger.error(
                f"Configuration file at {self.config_file_path} is completely empty."
            )
            return None

        # Resolve paths dynamically to handle real environment contexts smoothly
        output_base_dir = Path(lines[0])
        items_to_backup = lines[1:]
        return output_base_dir, items_to_backup


def main() -> None:
    """CLI Gateway transforming raw arguments into verified Pydantic contexts."""
    parser = argparse.ArgumentParser(
        description="Safely back up untracked local files."
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
            project_path=Path(args.project_path), verbose=args.verbose
        )
        success = manager.execute()
    except Exception as e:
        logger.error(f"Execution terminated due to validation breakdown: {e}")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
