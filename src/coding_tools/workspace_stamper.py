# src\coding-tools\workspace_stamper.py
"""Compliance engine for workspace files, managing license and path stamps."""

import argparse
import logging
import sys
from difflib import unified_diff
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, DirectoryPath, Field

logger = logging.getLogger("coding_tools.workspace_stamper")
logger.setLevel(logging.INFO)

# Global Engineering Constants
FILE_LICENSE = "LICENSE"
FILE_NOTICE = "NOTICE"
COPYRIGHT_TAG = "SPDX-FileCopyrightText"
LICENSE_TAG = "SPDX-License-Identifier"


class SPDXBlock(NamedTuple):
    """Encapsulates the structured text lines for SPDX injection."""

    copyright_line: str
    license_line: str

    def to_lines(self) -> list[str]:
        """Convert the SPDX block into raw formatted comment lines."""
        return [f"{self.copyright_line}\n", f"{self.license_line}\n"]


class TargetWorkspace(BaseModel):
    """Encapsulates and validates workspace paths and feature flag combinations."""

    project_dir: DirectoryPath
    target_path: Path
    run_path_stamp: bool = True
    run_license_stamp: bool = True
    extracted_copyright: str | None = Field(default=None, exclude=True)
    extracted_license_id: str | None = Field(default=None, exclude=True)

    def resolve_files(self) -> list[Path]:
        """Collect files safely, filtering out environments and caches."""
        if self.target_path.is_file():
            return [self.target_path] if self.target_path.suffix == ".py" else []

        if self.target_path.is_dir():
            return [
                f
                for f in self.target_path.rglob("*.py")
                if not any(
                    p in f.parts for p in (".venv", "venv", "__pycache__", ".git")
                )
            ]
        return []


class WorkspaceStamper(BaseModel):
    """Path-stamping and SPDX license metadata injection."""

    workspace: TargetWorkspace

    def run(self) -> bool:
        """Execute the verification engine, short-circuiting on validation anomalies."""
        logger.info(
            "Initializing compliance engine for target: %s",
            self.workspace.target_path,
        )

        if self.workspace.run_license_stamp:
            self._evaluate_legal_infrastructure()

        py_files = self.workspace.resolve_files()
        if not py_files:
            logger.info("No actionable Python targets identified.")
            return True

        baselines: dict[Path, str] = {}
        modified_count = 0

        for file_path in py_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                baselines[file_path] = content

                if self._process_file(file_path, content):
                    modified_count += 1
            except (UnicodeDecodeError, PermissionError) as e:
                logger.warning(
                    "I/O execution blocked for %s: %s",
                    file_path.name,
                    e,
                )

        logger.info(
            "Processed %d files. Mutated %d targets.",
            len(baselines),
            modified_count,
        )
        return self._verify_modifications(baselines)

    def _evaluate_legal_infrastructure(self) -> None:
        """Ensure presence of LICENSE/NOTICE and parses metadata dynamically."""
        license_file = self.workspace.project_dir / FILE_LICENSE
        notice_file = self.workspace.project_dir / FILE_NOTICE

        if not license_file.exists() or not notice_file.exists():
            logger.warning(
                "Compliance mismatch: '%s' or '%s' missing at project root (%s). "
                "Deactivating license stamping.",
                FILE_LICENSE,
                FILE_NOTICE,
                self.workspace.project_dir,
            )
            self.workspace.run_license_stamp = False
            return

        try:
            license_lines = license_file.read_text(encoding="utf-8").splitlines()
            title_candidates = [line.strip() for line in license_lines if line.strip()]
            if not title_candidates:
                logger.warning(
                    "The LICENSE file is completely empty. Deactivating "
                    "license stamping.",
                )
                self.workspace.run_license_stamp = False
                return

            raw_title = title_candidates[0]
            normalized = (
                raw_title.replace("License", "").replace("v", "").replace("Version", "")
            )
            parts = [p.strip() for p in normalized.split() if p.strip()]

            if not parts:
                logger.warning(
                    "Could not resolve a structural title within the LICENSE file.",
                )
                self.workspace.run_license_stamp = False
                return

            self.workspace.extracted_license_id = "-".join(parts)

            notice_text = notice_file.read_text(encoding="utf-8")
            for line in notice_text.splitlines():
                if "Copyright" in line:
                    clean_text = (
                        line.replace("Copyright", "")
                        .replace("(C)", "")
                        .replace("(c)", "")
                    )
                    clean_text = " ".join(clean_text.split())

                    self.workspace.extracted_copyright = (
                        f"# {COPYRIGHT_TAG}: {clean_text}"
                    )
                    logger.info(
                        "Extracted ID: %s | Copyright: %s",
                        self.workspace.extracted_license_id,
                        self.workspace.extracted_copyright,
                    )
                    return

            logger.warning(
                "Could not locate a valid 'Copyright' string sequence in %s.",
                FILE_NOTICE,
            )
            self.workspace.run_license_stamp = False
        except (OSError, ValueError) as e:
            logger.warning(
                "Failed parsing legal infrastructure: %s. "
                "Deactivating license stamping.",
                e,
            )
            self.workspace.run_license_stamp = False

    def _find_insertion_point(self, lines: list[str]) -> int:
        """Locate safe insertion point past interpreter lines."""
        idx = 0
        if idx < len(lines) and lines[idx].startswith("#!"):
            idx += 1
        if idx < len(lines) and any(c in lines[idx] for c in ("coding:", "coding=")):
            idx += 1
        return idx

    def _apply_path_stamp(
        self,
        file_path: Path,
        lines: list[str],
        idx: int,
    ) -> tuple[list[str], bool]:
        """Apply or purge top-of-file path comment macros."""
        is_modified = False
        new_lines = list(lines)
        if self.workspace.run_path_stamp:
            rel_path = file_path.relative_to(self.workspace.project_dir).as_posix()
            expected_path_line = f"# {rel_path}\n"

            if idx < len(new_lines) and new_lines[idx] == expected_path_line:
                pass
            elif (
                idx < len(new_lines)
                and new_lines[idx].startswith("#")
                and new_lines[idx].strip().endswith(".py")
            ):
                new_lines[idx] = expected_path_line
                is_modified = True
            else:
                new_lines.insert(idx, expected_path_line)
                is_modified = True
        elif (
            idx < len(new_lines)
            and new_lines[idx].startswith("#")
            and new_lines[idx].strip().endswith(".py")
        ):
            new_lines.pop(idx)
            is_modified = True
        return new_lines, is_modified

    def _apply_license_stamp(
        self,
        lines: list[str],
        idx: int,
    ) -> tuple[list[str], bool]:
        """Apply or purge SPDX license compliance definitions."""
        is_modified = False
        new_lines = list(lines)
        if self.workspace.run_license_stamp and self.workspace.extracted_copyright:
            block = SPDXBlock(
                copyright_line=self.workspace.extracted_copyright,
                license_line=(
                    f"# {LICENSE_TAG}: {self.workspace.extracted_license_id}"
                ),
            )

            if (
                idx + 1 < len(new_lines)
                and new_lines[idx].strip() == block.copyright_line
                and new_lines[idx + 1].strip() == block.license_line
            ):
                return new_lines, is_modified

            new_lines, purge_mod = self._purge_legacy_tags(new_lines, idx)
            if purge_mod:
                is_modified = True

            new_lines.insert(idx, block.license_line + "\n")
            new_lines.insert(idx, block.copyright_line + "\n")
            is_modified = True
        elif not self.workspace.run_license_stamp:
            new_lines, purge_mod = self._purge_legacy_tags(new_lines, idx)
            if purge_mod:
                is_modified = True
        return new_lines, is_modified

    def _purge_legacy_tags(
        self,
        lines: list[str],
        idx: int,
    ) -> tuple[list[str], bool]:
        """Identify and slice out legacy tags within reasonable bounds."""
        is_modified = False
        new_lines = list(lines)
        lookahead = min(len(new_lines), idx + 4)
        purge_indices = [
            i
            for i in range(idx, lookahead)
            if COPYRIGHT_TAG in new_lines[i] or LICENSE_TAG in new_lines[i]
        ]
        for offset, target_purge in enumerate(purge_indices):
            new_lines.pop(target_purge - offset)
            is_modified = True
        return new_lines, is_modified

    def _generate_updated_content(
        self,
        file_path: Path,
        content: str,
    ) -> tuple[str, bool]:
        """Calculate file layouts dynamically based on state configurations."""
        lines = content.splitlines(keepends=True)
        is_modified = False

        idx = self._find_insertion_point(lines)
        lines, path_mod = self._apply_path_stamp(file_path, lines, idx)
        if path_mod:
            is_modified = True

        if self.workspace.run_path_stamp:
            idx += 1

        lines, lic_mod = self._apply_license_stamp(lines, idx)
        if lic_mod:
            is_modified = True

        return "".join(lines), is_modified

    def _process_file(self, file_path: Path, content: str) -> bool:
        """Save structural transformations down to physical media safely."""
        try:
            new_content, is_modified = self._generate_updated_content(
                file_path,
                content,
            )
            if is_modified:
                file_path.write_text(new_content, encoding="utf-8")
                return True
        except OSError:
            logger.exception("Failed execution lifecycle on target %s", file_path.name)
        return False

    def _verify_modifications(self, baselines: dict[Path, str]) -> bool:
        """Verify that only explicitly authorized changes took place."""
        errors: list[str] = []

        for path, original_content in baselines.items():
            current_content = path.read_text(encoding="utf-8")
            if original_content == current_content:
                continue

            diff = list(
                unified_diff(
                    original_content.splitlines(),
                    current_content.splitlines(),
                    lineterm="",
                ),
            )
            content_changes = [
                diff_line
                for diff_line in diff
                if diff_line.startswith(("+", "-"))
                and not diff_line.startswith(("+++", "---"))
            ]

            for change in content_changes:
                stripped = change[1:].strip()

                if ".py" in change and change.startswith(("-#", "+#")):
                    continue
                if COPYRIGHT_TAG in stripped or LICENSE_TAG in stripped:
                    continue

                errors.append(
                    f"[{path.name}] Unauthorized syntax variance intercepted: {change}",
                )

        if errors:
            logger.critical("SAFETY ENGINE ALERT: EXTRANEOUS FILE MUTATIONS LOGGED!")
            for err in errors:
                logger.error("%s", err)
            return False

        logger.info("Workspace verification engine completed layout with zero faults.")
        return True


def main() -> None:
    """CLI Executive Run Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Enforces workspace layouts, path stamps, and legal headers.",
    )
    parser.add_argument(
        "target",
        type=str,
        help="Target system path (.py file or folder workspace directory).",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        required=True,
        help="Root anchor location housing LICENSE/NOTICE.",
    )
    parser.add_argument(
        "--no-path",
        action="store_true",
        help="Bypass or strip top-of-file path comment macros.",
    )
    parser.add_argument(
        "--no-license",
        action="store_true",
        help="Bypass or strip structural SPDX compliance strings.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        workspace = TargetWorkspace(
            project_dir=Path(args.project_dir),
            target_path=Path(args.target),
            run_path_stamp=not args.no_path,
            run_license_stamp=not args.no_license,
        )
        stamper = WorkspaceStamper(workspace=workspace)
        success = stamper.run()
    except (OSError, ValueError):
        logger.exception("Runtime execution roadblock encountered.")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
