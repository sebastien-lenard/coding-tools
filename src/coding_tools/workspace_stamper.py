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


class CodeStamperEngine(BaseModel):
    """Path-stamping and SPDX license metadata injection."""

    workspace: TargetWorkspace

    def run(self) -> bool:
        """Execute the verification engine, short-circuiting on validation anomalies."""
        logger.info(
            f"Initializing compliance engine for target: {self.workspace.target_path}",
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
                logger.warning(f"I/O execution blocked for {file_path.name}: {e}")

        logger.info(
            f"Processed {len(baselines)} files. Mutated {modified_count} targets.",
        )
        return self._verify_modifications(baselines)

    def _evaluate_legal_infrastructure(self) -> None:
        """Ensure presence of LICENSE/NOTICE and parses metadata dynamically."""
        license_file = self.workspace.project_dir / FILE_LICENSE
        notice_file = self.workspace.project_dir / FILE_NOTICE

        if not license_file.exists() or not notice_file.exists():
            logger.warning(
                f"Compliance mismatch: '{FILE_LICENSE}' or '{FILE_NOTICE}' missing "
                f"at project root ({self.workspace.project_dir}). Deactivating license stamping.",
            )
            self.workspace.run_license_stamp = False
            return

        try:
            # 1. Truly Dynamic LICENSE Parsing via Structural Extraction
            license_lines = license_file.read_text(encoding="utf-8").splitlines()

            # Filter empty lines and locate the title block header (usually line 1 or 2)
            title_candidates = [line.strip() for line in license_lines if line.strip()]
            if not title_candidates:
                logger.warning(
                    "The LICENSE file is completely empty. Deactivating license stamping.",
                )
                self.workspace.run_license_stamp = False
                return

            raw_title = title_candidates[0]

            # Normalize title chunks into a standardized SPDX lookalike slug
            # e.g., "Apache License Version 2.0" -> "Apache-2.0"
            # e.g., "MIT License" -> "MIT"
            # e.g., "BSD 3-Clause License" -> "BSD-3-Clause"
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

            # Combine elements cleanly with standard SPDX dash joins
            # e.g., ['Apache', '2.0'] -> 'Apache-2.0'
            self.workspace.extracted_license_id = "-".join(parts)

            # 2. Dynamically extract copyright line from NOTICE
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
                        f"Extracted metadata elements -> ID: {self.workspace.extracted_license_id} | "
                        f"Copyright: {self.workspace.extracted_copyright}",
                    )
                    return

            logger.warning(
                f"Could not locate a valid 'Copyright' string sequence in {FILE_NOTICE}.",
            )
            self.workspace.run_license_stamp = False
        except Exception as e:
            logger.warning(
                f"Failed parsing legal infrastructure: {e}. Deactivating license stamping.",
            )
            self.workspace.run_license_stamp = False

    def _generate_updated_content(
        self,
        file_path: Path,
        content: str,
    ) -> tuple[str, bool]:
        """Calculate file layouts dynamically based on state configurations."""
        lines = content.splitlines(keepends=True)
        is_modified = False

        # 1. Locate safe insertion point past interpreters
        idx = 0
        if idx < len(lines) and lines[idx].startswith("#!"):
            idx += 1
        if idx < len(lines) and any(c in lines[idx] for c in ("coding:", "coding=")):
            idx += 1

        # 2. Path Stamp Layer Implementation
        if self.workspace.run_path_stamp:
            rel_path = file_path.relative_to(self.workspace.project_dir).as_posix()
            expected_path_line = f"# {rel_path}\n"

            if idx < len(lines) and lines[idx] == expected_path_line:
                pass  # Perfectly aligned
            elif (
                idx < len(lines)
                and lines[idx].startswith("#")
                and lines[idx].strip().endswith(".py")
            ):
                lines[idx] = expected_path_line
                is_modified = True
            else:
                lines.insert(idx, expected_path_line)
                is_modified = True

            idx += 1
        elif (
            idx < len(lines)
            and lines[idx].startswith("#")
            and lines[idx].strip().endswith(".py")
        ):
            lines.pop(idx)
            is_modified = True

        # 3. SPDX License Injection Layer Implementation
        if self.workspace.run_license_stamp and self.workspace.extracted_copyright:
            block = SPDXBlock(
                copyright_line=self.workspace.extracted_copyright,
                license_line=(
                    f"# {LICENSE_TAG}: {self.workspace.extracted_license_id}"
                ),
            )

            if (
                idx + 1 < len(lines)
                and lines[idx].strip() == block.copyright_line
                and lines[idx + 1].strip() == block.license_line
            ):
                return "".join(lines), is_modified

            # Purge dirty/legacy indicators up front
            lookahead = min(len(lines), idx + 4)
            purge_indices = [
                i
                for i in range(idx, lookahead)
                if COPYRIGHT_TAG in lines[i] or LICENSE_TAG in lines[i]
            ]
            for offset, target_purge in enumerate(purge_indices):
                lines.pop(target_purge - offset)
                is_modified = True

            # Insert clean blocks down stream
            lines.insert(idx, block.license_line + "\n")
            lines.insert(idx, block.copyright_line + "\n")
            is_modified = True

        elif not self.workspace.run_license_stamp:
            lookahead = min(len(lines), idx + 4)
            purge_indices = [
                i
                for i in range(idx, lookahead)
                if COPYRIGHT_TAG in lines[i] or LICENSE_TAG in lines[i]
            ]
            if purge_indices:
                for offset, target_purge in enumerate(purge_indices):
                    lines.pop(target_purge - offset)
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
        except Exception:
            logger.exception(f"Failed execution lifecycle on target {file_path.name}")
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
            # Ruff E741 Fixed: variable renamed from 'l' to 'diff_line'
            content_changes = [
                diff_line
                for diff_line in diff
                if diff_line.startswith(("+", "-"))
                and not diff_line.startswith(("+++", "---"))
            ]

            for change in content_changes:
                stripped = change[1:].strip()

                if ".py" in change and (
                    change.startswith("-#") or change.startswith("+#")
                ):
                    continue
                if COPYRIGHT_TAG in stripped or LICENSE_TAG in stripped:
                    continue

                errors.append(
                    f"[{path.name}] Unauthorized syntax variance intercepted: {change}",
                )

        if errors:
            logger.critical("SAFETY ENGINE ALERT: EXTRANEOUS FILE MUTATIONS LOGGED!")
            for err in errors:
                logger.error(err)
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
        stamper = CodeStamperEngine(workspace=workspace)
        success = stamper.run()
    except Exception:
        logger.exception("Runtime execution roadblock encountered.")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
