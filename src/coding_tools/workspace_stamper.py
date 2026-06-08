import argparse
import logging
import sys
from difflib import unified_diff
from pathlib import Path

from pydantic import BaseModel, DirectoryPath

logger = logging.getLogger("coding_tools.path_stamper")
logger.setLevel(logging.INFO)


class PathStamper(BaseModel):
    """Automates and validates top-of-file relative path headers for Python scripts."""

    project_dir: DirectoryPath

    def run(self) -> bool:
        """Orchestrates the stamping workflow and validates modifications for safety."""
        logger.info(f"Initializing path stamping for directory: {self.project_dir}")
        py_files = self._scan_files()

        if not py_files:
            logger.info("No target Python files identified to process.")
            return True

        # Snapshot baseline file contents before modification for safe validation
        baselines: dict[Path, str] = {}
        for file_path in py_files:
            try:
                baselines[file_path] = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError) as e:
                logger.warning(
                    f"Skipping file due to read permissions/encoding: "
                    f"{file_path.name} ({e})"
                )

        modified_count = 0
        for file_path, original_content in baselines.items():
            if self._stamp_file(file_path, original_content):
                modified_count += 1

        logger.info(
            f"Processed {len(baselines)} files. Modified {modified_count} targets."
        )

        # Validate structural changes safely without regex string parsing
        return self._verify_modifications(baselines)

    def _scan_files(self) -> list[Path]:
        """Finds all project python files excluding virtual environments."""
        return [
            f
            for f in self.project_dir.rglob("*.py")
            if not any(part in f.parts for part in (".venv", "venv", "__pycache__"))
        ]

    def _generate_updated_content(
        self, content: str, rel_path_str: str
    ) -> tuple[str, bool]:
        """Inserts or overwrites the relative path macro at the top of the file."""
        lines = content.splitlines(keepends=True)
        expected_header = f"# {rel_path_str}\n"

        if not lines:
            return expected_header, True

        # Find safe insertion index past shebangs or encoding cookies
        idx = 0
        if lines[idx].startswith("#!"):
            idx += 1
        if idx < len(lines) and any(x in lines[idx] for x in ("coding:", "coding=")):
            idx += 1

        # Check if the header is already correctly set
        if idx < len(lines) and lines[idx].strip() == expected_header.strip():
            return content, False

        # If an outdated or alternative structural path header is already there,
        # overwrite it
        if idx < len(lines) and lines[idx].startswith("#") and (".py" in lines[idx]):
            lines[idx] = expected_header
        else:
            lines.insert(idx, expected_header)

        return "".join(lines), True

    def _stamp_file(self, file_path: Path, original_content: str) -> bool:
        """Handles the localized write mutation lifecycle for a target script."""
        try:
            rel_path = file_path.relative_to(self.project_dir)
            new_content, is_modified = self._generate_updated_content(
                original_content, rel_path.as_posix()
            )

            if is_modified:
                file_path.write_text(new_content, encoding="utf-8")
                logger.info(f"Updated header path: {rel_path.as_posix()}")
                return True
        except Exception as e:
            logger.error(f"Failed writing script updates to {file_path.name}: {e}")
        return False

    def _verify_modifications(self, baselines: dict[Path, str]) -> bool:
        """Ensures that the only changes are explicit header path comments."""
        errors: list[str] = []

        for file_path, original_content in baselines.items():
            current_content = file_path.read_text(encoding="utf-8")
            if original_content == current_content:
                continue

            diff = list(
                unified_diff(
                    original_content.splitlines(),
                    current_content.splitlines(),
                    lineterm="",
                )
            )

            # A clean stamp operation should only yield lines showing the replacement
            # Filter diff metadata out to evaluate actual content mutations
            content_changes = [
                line
                for line in diff
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            ]

            for change in content_changes:
                # If a line deletion (-) wasn't an old header macro, or an addition (+)
                # isn't a new one
                if change.startswith("-") and not (
                    ".py" in change and change.strip().startswith("-#")
                ):
                    errors.append(
                        f"[{file_path.name}] Unsafe line removal detected: {change}"
                    )
                elif change.startswith("+") and not (
                    change.strip().startswith("+#") and ".py" in change
                ):
                    errors.append(
                        f"[{file_path.name}] Unsafe line addition detected: {change}"
                    )

        if errors:
            logger.error("CRITICAL ERROR: SAFETY VALIDATION FAILED!")
            for error in errors:
                logger.error(f"Structural Deviation: {error}")
            return False

        logger.info("Success: All structural safety validation checks passed cleanly.")
        return True


def main() -> None:
    """CLI Entrypoint processing runtime arguments."""
    parser = argparse.ArgumentParser(description="Automate file path headers safely.")
    parser.add_argument("project_dir", type=str, help="Root folder system path.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        stamper = PathStamper(project_dir=Path(args.project_dir))
        success = stamper.run()
    except Exception as e:
        logger.error(f"Runtime roadblock encountered: {e}")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
