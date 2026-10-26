# src/coding_tools/workspace_stamper.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Inject SPDX license and path stamps into files.

Reads root LICENSE and NOTICE files.
"""

from __future__ import annotations

import argparse
import re
import sys
from difflib import unified_diff
from enum import Enum, auto
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, DirectoryPath, Field

from coding_tools import my_logger

logger = my_logger.logger(__name__)

# Global Engineering Constants
FILE_LICENSE = "LICENSE"
FILE_NOTICE = "NOTICE"
COPYRIGHT_TAG = "SPDX-FileCopyrightText"
LICENSE_TAG = "SPDX-License-Identifier"


class FileComplianceStatus(Enum):
    """File compliance states for stamp injection."""

    COMPLIANT = auto()  # File is already properly formatted; no-op.
    MUTATED = auto()  # File was out of compliance but safely updated.
    BLOCKED_MUTATION = auto()  # Safety module blocked unauthorized code changes.
    IO_ERROR = auto()  # System-level permissions or write failure.


class FileProcessReport(NamedTuple):
    """Result of file processing."""

    file_path: Path
    status: FileComplianceStatus


class TargetWorkspace(BaseModel):
    """Workspace path configuration and feature flags."""

    project_dir: DirectoryPath
    target_path: Path
    run_path_stamp: bool = True
    run_license_stamp: bool = True
    extracted_copyright: str | None = Field(default=None, exclude=True)
    extracted_license_id: str | None = Field(default=None, exclude=True)

    def resolve_files(self) -> list[Path]:
        """Get list of Python files. Skips virtual envs and caches."""
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
    """Inject path stamp and SPDX license metadata into files. Check content changes."""

    workspace: TargetWorkspace

    def run(self) -> bool:
        """Run header check and write file reports.

        Fails if blocked changes or I/O errors occur.
        """
        func = f"{__name__}"
        logger.start(func, target=self.workspace.target_path)

        if self.workspace.run_license_stamp:
            self._evaluate_legal_infrastructure()

        py_files = self.workspace.resolve_files()
        if not py_files:
            logger.progress(
                self.workspace.target_path,
                "No files to scan",
            )
            return True

        reports: list[FileProcessReport] = []

        for file_path in py_files:
            report = self._process_file(file_path)
            reports.append(report)

        # Executive Metrics Aggregation
        total_processed = len(reports)
        mutated_count = sum(
            1 for r in reports if r.status == FileComplianceStatus.MUTATED
        )
        compliant_count = sum(
            1 for r in reports if r.status == FileComplianceStatus.COMPLIANT
        )
        blocked_count = sum(
            1 for r in reports if r.status == FileComplianceStatus.BLOCKED_MUTATION
        )
        io_errors_count = sum(
            1 for r in reports if r.status == FileComplianceStatus.IO_ERROR
        )

        logger.summary_line(
            "Stamp Summary:",
            ["Scanned", "OK", "Edited", "Blocked", "Errors"],
            [
                str(total_processed),
                str(compliant_count),
                str(mutated_count),
                str(blocked_count),
                str(io_errors_count),
            ],
        )

        logger.end(func, target=self.workspace.target_path)
        return not (blocked_count > 0 or io_errors_count > 0)

    def _evaluate_legal_infrastructure(self) -> None:
        """Read root LICENSE and NOTICE files to extract copyright and license ID."""
        license_file = self.workspace.project_dir / FILE_LICENSE
        notice_file = self.workspace.project_dir / FILE_NOTICE

        if not license_file.exists():
            logger.warning(
                None,
                f"Missing '{FILE_LICENSE}' in {self.workspace.project_dir}",
            )
        else:
            try:
                lines = license_file.read_text(encoding="utf-8").splitlines()
                first_two = [line.strip() for line in lines[:2] if line.strip()]
                logger.progress(FILE_LICENSE, "Caught headers", " | ".join(first_two))
            except OSError as e:
                logger.warning(FILE_LICENSE, f"Failed to read file: {e}")

        if not notice_file.exists():
            logger.warning(
                None,
                f"Missing '{FILE_NOTICE}' in {self.workspace.project_dir}",
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
                        FILE_NOTICE,
                        "Missing 'Copyright'.",
                    )
            except OSError as e:
                logger.warning(FILE_NOTICE, f"Failed to read file: {e}")

    def _find_insertion_point(self, lines: list[str]) -> int:
        """Find file insertion point past shebang and encoding lines."""
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
        """Add or clear top-of-file path comment."""
        is_modified = False
        new_lines = list(lines)
        if self.workspace.run_path_stamp:
            try:
                rel_path = file_path.relative_to(self.workspace.project_dir).as_posix()
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
        """Add or clear SPDX license and copyright tags."""
        is_modified = False
        new_lines = list(lines)
        if self.workspace.run_license_stamp:
            license_line = f"# {LICENSE_TAG}: {self.workspace.extracted_license_id}"
            copyright_block = self.workspace.extracted_copyright

            if copyright_block is not None:
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
        """Clear legacy copyright and license tags from file comments."""
        is_modified = False
        new_lines = list(lines)
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
        """Yield updated file content with path and license stamps."""
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

    def _process_file(self, file_path: Path) -> FileProcessReport:
        """Process file and return report. Write file if changed.

        Catch OS and permission errors.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            new_content, is_modified = self._generate_updated_content(
                file_path,
                content,
            )

            if not is_modified:
                return FileProcessReport(file_path, FileComplianceStatus.COMPLIANT)

            if not self._is_mutation_authorized(
                file_path,
                content,
                new_content,
            ):
                return FileProcessReport(
                    file_path,
                    FileComplianceStatus.BLOCKED_MUTATION,
                )

            file_path.write_text(new_content, encoding="utf-8")
            return FileProcessReport(file_path, FileComplianceStatus.MUTATED)

        except (OSError, UnicodeDecodeError, PermissionError):
            logger.exception(
                file_path,
                "Failed run of process_file()",
            )
            return FileProcessReport(file_path, FileComplianceStatus.IO_ERROR)

    def _is_mutation_authorized(
        self,
        file_path: Path,
        original_content: str,
        new_content: str,
    ) -> bool:
        """Check if file edits involve only path or license comments."""
        orig_normalized = original_content.replace("\r\n", "\n").splitlines()
        new_normalized = new_content.replace("\r\n", "\n").splitlines()

        diff = list(unified_diff(orig_normalized, new_normalized, lineterm=""))
        content_changes = [
            diff_line
            for diff_line in diff
            if diff_line.startswith(("+", "-"))
            and not diff_line.startswith(("+++", "---"))
        ]

        errors: list[str] = []
        for change in content_changes:
            stripped = change[1:].strip()

            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if COPYRIGHT_TAG in stripped or LICENSE_TAG in stripped:
                continue

            errors.append(
                f"[{file_path.name}] Banned syntax edit: {change}",
            )

        if errors:
            logger.error(
                file_path,
                "Spotted banned changes",
            )
            for err in errors:
                logger.error(file_path, err)
            return False

        return True


def validate_license_id(license_id: str) -> bool:
    """Check if license ID has only valid alphanumeric and symbol characters."""
    return all(c.isalnum() or c in "-.+" for c in license_id)


def strip_header(txt: str) -> str:
    """Strip HTML comment headers."""
    return re.sub(r"^(?:[ \t]*<!--.*?-->[ \t]*\s*)+", "", txt, flags=re.DOTALL).strip()


def main() -> None:
    """Run CLI argument parser and execute workspace stamper."""
    parser = argparse.ArgumentParser(
        description="Applies workspace layouts, path stamps, and license header",
    )
    parser.add_argument(
        "target",
        type=str,
        help="Target path (.py file or folder workspace dir)",
    )
    parser.add_argument(
        "--project-dir",
        "-p",
        type=str,
        required=False,
        help="Root path of LICENSE/NOTICE",
    )
    parser.add_argument(
        "--license-id",
        "-l",
        type=str,
        required=False,
        help="Target SPDX-License-Identifier",
    )
    parser.add_argument(
        "--no-path",
        action="store_true",
        help="Bypass or strip top-of-file path comment",
    )
    parser.add_argument(
        "--no-license",
        action="store_true",
        help="Bypass or strip SPDX comments",
    )
    args = parser.parse_args()

    my_logger.setup()

    if args.no_path and args.no_license:
        logger.warning(
            None,
            "End. No stamping due to --no-path and --no-license flags",
        )
        sys.exit(0)

    if not args.no_license:
        if not args.license_id:
            logger.error(
                None,
                "Missing --license-id / -l (needed unless --no-license)",
            )
            sys.exit(1)
        if not validate_license_id(args.license_id):
            logger.error(
                None,
                f"Bad letters in license ID '{args.license_id}'. "
                f"Accepts alphanumeric, dashes (-), dots (.), and plus signs (+)",
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
                None,
                "Missing --project-dir (needed when target is a file and "
                "no --no-license flag)",
            )
            sys.exit(1)
        else:
            project_dir = target_path.parent.resolve()
    else:
        project_dir = Path(args.project_dir).resolve()

    if not project_dir.is_dir():
        logger.error(None, f"Bad project dir: {project_dir}")
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
        logger.exception(None, "End. Failed run of workspace-stamper")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
