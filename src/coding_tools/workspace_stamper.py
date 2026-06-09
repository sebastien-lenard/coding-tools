# workspace_stamper.py
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
        """Execute the verification engine, validating in-memory before writing."""
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

        modified_count = 0
        total_processed = 0
        has_safety_faults = False

        for file_path in py_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                total_processed += 1

                status, is_modified = self._process_file(file_path, content)
                if not status:
                    has_safety_faults = True
                elif is_modified:
                    modified_count += 1

            except (UnicodeDecodeError, PermissionError) as e:
                logger.warning(
                    "I/O execution blocked for %s: %s",
                    file_path.name,
                    e,
                )

        logger.info(
            "Processed %d files. Mutated %d targets.",
            total_processed,
            modified_count,
        )
        return not has_safety_faults

    def _evaluate_legal_infrastructure(self) -> None:
        """Process legal headers, logging file contents without blocking updates."""
        license_file = self.workspace.project_dir / FILE_LICENSE
        notice_file = self.workspace.project_dir / FILE_NOTICE

        if not license_file.exists():
            logger.warning(
                "Compliance notice: '%s' is missing from project root (%s).",
                FILE_LICENSE,
                self.workspace.project_dir,
            )
        else:
            try:
                lines = license_file.read_text(encoding="utf-8").splitlines()
                first_two = [line.strip() for line in lines[:2] if line.strip()]
                logger.info("LICENSE headers detected: %s", " | ".join(first_two))
            except OSError as e:
                logger.warning("Could not read LICENSE file: %s", e)

        if not notice_file.exists():
            logger.warning(
                "Compliance notice: '%s' is missing from project root (%s).",
                FILE_NOTICE,
                self.workspace.project_dir,
            )
        else:
            try:
                notice_text = notice_file.read_text(encoding="utf-8")
                copyright_lines = []
                for line in notice_text.splitlines():
                    if "Copyright" in line:
                        clean_text = (
                            line.replace("Copyright", "")
                            .replace("(C)", "")
                            .replace("(c)", "")
                        )
                        clean_text = " ".join(clean_text.split())
                        copyright_lines.append(f"# {COPYRIGHT_TAG}: {clean_text}")

                if copyright_lines:
                    self.workspace.extracted_copyright = "\n".join(copyright_lines)
                else:
                    logger.warning(
                        "Could not locate a valid 'Copyright' string sequence in %s.",
                        FILE_NOTICE,
                    )
            except OSError as e:
                logger.warning("Could not read NOTICE file: %s", e)

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
            try:
                rel_path = file_path.relative_to(
                    self.workspace.project_dir,
                ).as_posix()
                expected_path_line = f"# {rel_path}\n"
            except ValueError:
                expected_path_line = f"# {file_path.name}\n"

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
        if self.workspace.run_license_stamp:
            license_line = f"# {LICENSE_TAG}: {self.workspace.extracted_license_id}"
            copyright_block = self.workspace.extracted_copyright

            if copyright_block is not None:
                # Ensure each extracted copyright line is properly formatted as a comment line
                copyright_lines = [
                    f"{line}\n" if line.startswith("#") else f"# {line}\n"
                    for line in copyright_block.splitlines()
                ]
                req_len = len(copyright_lines) + 1
                if idx + req_len <= len(new_lines):
                    existing_chunk = new_lines[idx : idx + req_len]
                    expected_chunk = [*copyright_lines, license_line + "\n"]
                    if [line.strip() for line in existing_chunk] == [
                        line.strip() for line in expected_chunk
                    ]:
                        return new_lines, is_modified
            elif idx < len(new_lines) and new_lines[idx].strip() == license_line:
                return new_lines, is_modified

            new_lines, purge_mod = self._purge_legacy_tags(new_lines, idx)
            if purge_mod:
                is_modified = True

            new_lines.insert(idx, license_line + "\n")
            if copyright_block is not None:
                for line in reversed(copyright_block.splitlines()):
                    comment_line = line if line.startswith("#") else f"# {line}"
                    new_lines.insert(idx, comment_line + "\n")
            is_modified = True
        else:
            new_lines, purge_mod = self._purge_legacy_tags(new_lines, idx)
            if purge_mod:
                is_modified = True
        return new_lines, is_modified

    def _purge_legacy_tags(
        self,
        lines: list[str],
        idx: int,
    ) -> tuple[list[str], bool]:
        """Identify and slice out legacy tags within comments safely."""
        is_modified = False
        new_lines = list(lines)
        # Extended window for multi-holder text
        lookahead = min(len(new_lines), idx + 10)
        purge_indices = [
            i
            for i in range(idx, lookahead)
            if new_lines[i].lstrip().startswith("#")
            and (COPYRIGHT_TAG in new_lines[i] or LICENSE_TAG in new_lines[i])
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

    def _process_file(self, file_path: Path, content: str) -> tuple[bool, bool]:
        """Check transformations in-memory and write changes atomically if clear."""
        try:
            new_content, is_modified = self._generate_updated_content(
                file_path,
                content,
            )
            if is_modified:
                if not self._is_mutation_authorized(file_path, content, new_content):
                    return False, False
                file_path.write_text(new_content, encoding="utf-8")
            else:
                return True, is_modified
        except OSError:
            logger.exception("Failed execution lifecycle on target %s", file_path.name)
        return False, False

    def _is_mutation_authorized(
        self,
        file_path: Path,
        original_content: str,
        new_content: str,
    ) -> bool:
        """Enforce strict safety verification checks dynamically in-memory."""
        diff = list(
            unified_diff(
                original_content.splitlines(),
                new_content.splitlines(),
                lineterm="",
            ),
        )
        content_changes = [
            diff_line
            for diff_line in diff
            if diff_line.startswith(("+", "-"))
            and not diff_line.startswith(("+++", "---"))
        ]

        errors: list[str] = []
        for change in content_changes:
            # Strip the leading +/- indicator
            action = change[0]
            line_content = change[1:]
            stripped = line_content.strip()

            # Ignore entirely empty lines changed at top of file layout
            if not stripped:
                continue
            # Ignore any comment line modifications safely
            if stripped.startswith("#"):
                continue
            # Ignore tags anywhere in the mutation sequence
            if COPYRIGHT_TAG in stripped or LICENSE_TAG in stripped:
                continue

            errors.append(
                f"[{file_path.name}] Unauthorized syntax variance intercepted:"
                " {change}",
            )

        if errors:
            logger.critical("SAFETY ENGINE ALERT: EXTRANEOUS FILE MUTATIONS LOGGED!")
            for err in errors:
                logger.error("%s", err)
            return False

        return True


def validate_license_id(license_id: str) -> bool:
    """Check if license_id contains only alphanumericals, dashes, dots, or plus sign."""
    return all(c.isalnum() or c in "-.+" for c in license_id)


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
        "-p",
        type=str,
        required=False,
        help="Root anchor location housing LICENSE/NOTICE.",
    )
    parser.add_argument(
        "--license-id",
        "-l",
        type=str,
        required=False,
        help="SPDX-License-Identifier constraint target.",
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

    if args.no_path and args.no_license:
        logger.info(
            "Both --no-path and --no-license flags are active. "
            "No stamping will be carried out.",
        )
        sys.exit(0)

    if not args.no_license:
        if not args.license_id:
            logger.error("Argument --license-id / -l is required unless --no-license.")
            sys.exit(1)
        if not validate_license_id(args.license_id):
            logger.error(
                "Invalid characters in license ID '%s'. Only alphanumeric, "
                "dashes (-), dots (.), and plus signs (+) are allowed.",
                args.license_id,
            )
            sys.exit(1)

    target_path = Path(args.target).resolve()

    if target_path.is_dir():
        project_dir = (
            Path(args.project_dir).resolve() if args.project_dir else target_path
        )
    elif not args.project_dir:
        if not args.no_license:
            logger.error(
                "Argument --project-dir is required when target is a file "
                "and licensing is enabled.",
            )
            sys.exit(1)
        else:
            project_dir = target_path.parent.resolve()
    else:
        project_dir = Path(args.project_dir).resolve()

    if not project_dir.is_dir():
        logger.error("Resolved project directory is invalid: %s", project_dir)
        sys.exit(1)

    try:
        workspace = TargetWorkspace(
            project_dir=project_dir,
            target_path=target_path,
            run_path_stamp=not args.no_path,
            run_license_stamp=not args.no_license,
            extracted_license_id=args.license_id,
        )
        stamper = WorkspaceStamper(workspace=workspace)
        success = stamper.run()
    except (OSError, ValueError):
        logger.exception("Runtime execution roadblock encountered.")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
