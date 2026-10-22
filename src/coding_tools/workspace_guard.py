# src/coding_tools/workspace_guard.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Guard module checking for static test isolation and runtime workspace pollution."""

from __future__ import annotations

import argparse
import ast
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, DirectoryPath

logger = logging.getLogger("coding_tools.workspace_guard")

IGNORED_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}
CHECKED_EXTENSIONS = {".py"}


class WorkspaceGuard(BaseModel):
    """Enforces test file isolation and prevents workspace file pollution."""

    project_path: DirectoryPath

    def check_static_isolation(
        self,
        test_file_path: str | Path,
        prefix: str = "Guard",
    ) -> tuple[bool, list[str]]:
        """Inspect test file AST to ensure test functions use tmp_path for I/O."""
        path = Path(test_file_path)
        if not path.exists():
            logger.warning(
                "[%s] Static check skipped: Test file not found at %s",
                prefix,
                path,
            )
            return True, []

        logger.info(
            "[%s] Running static isolation check on test file: %s",
            prefix,
            path,
        )
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            logger.exception("[%s] SyntaxError during static AST inspection", prefix)
            return False, [f"SyntaxError during AST inspection: {e}"]

        violations: list[str] = []

        class IsolationVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                if node.name.startswith("test_"):
                    has_tmp_path = any(
                        arg.arg in ("tmp_path", "setup_mock_project")
                        for arg in node.args.args
                    )
                    has_io = any(
                        isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr
                        in (
                            "write_text",
                            "write_bytes",
                            "mkdir",
                            "open",
                        )
                        for n in ast.walk(node)
                    )
                    if has_io and not has_tmp_path:
                        violations.append(
                            f"Test function `{node.name}` performs file I/O "
                            "or directory creation without the `tmp_path` "
                            "(or sandbox fixture) parameter.",
                        )
                self.generic_visit(node)

        IsolationVisitor().visit(tree)
        if violations:
            logger.warning(
                "[%s] Static isolation violations detected in %s",
                prefix,
                path,
            )
        else:
            logger.info("[%s] Static isolation check passed for %s", prefix, path)

        return len(violations) == 0, violations

    def snapshot_workspace(self, prefix: str = "Guard") -> set[Path]:
        """Capture a set of all current relative file paths across the repo."""
        logger.info(
            "[%s] Snapshotting workspace repository at: %s",
            prefix,
            self.project_path,
        )
        snapshot: set[Path] = set()
        for p in self.project_path.rglob("*"):
            if any(part in IGNORED_DIRS for part in p.parts):
                continue
            if p.is_file() and p.suffix in CHECKED_EXTENSIONS:
                try:
                    rel = p.relative_to(self.project_path)
                    snapshot.add(rel)
                except ValueError:
                    continue
        logger.info(
            "[%s] Workspace snapshot captured (%d Python files tracked).",
            prefix,
            len(snapshot),
        )
        return snapshot

    def check_runtime_pollution(
        self,
        baseline: set[Path],
        prefix: str = "Guard",
    ) -> tuple[bool, list[str]]:
        """Compare current workspace against baseline to detect new files."""
        logger.info("[%s] Checking for runtime workspace pollution...", prefix)
        current = self.snapshot_workspace(prefix)
        new_files = current - baseline

        violations: list[str] = []
        unauthorized_list: list[str] = []
        for f in new_files:
            if f.parent == Path() and (
                f.name.startswith("unit-test-")
                or f.name.startswith("based-pyright-")
                or f.name.startswith("ruff-")
            ):
                continue
            unauthorized_list.append(str(f))
            violations.append(
                f"Unauthorized file pollution detected in workspace: {f}",
            )

        if violations:
            logger.warning(
                "[%s] Runtime workspace pollution detected "
                "(%d unauthorized Python files: %s).",
                prefix,
                len(violations),
                unauthorized_list,
            )
        else:
            logger.info(
                "[%s] Runtime workspace pollution check passed cleanly.",
                prefix,
            )

        return len(violations) == 0, violations

    def execute_test_and_guard(
        self,
        test_file_path: str | Path,
        prefix: str = "Guard",
        *,
        run_coverage: bool = False,
        source_file_path: str | Path | None = None,
    ) -> tuple[bool, list[str]]:
        """Capture baseline, run pytest on the test file, and check pollution."""
        baseline = self.snapshot_workspace(prefix)
        path = Path(test_file_path)
        test_stem = path.stem

        cmd_list = [
            "uv",
            "run",
            "pytest",
            "--import-mode=importlib",
        ]
        if run_coverage and source_file_path:
            source_path = Path(source_file_path)
            try:
                relative_source = source_path.relative_to("src")
            except ValueError:
                relative_source = source_path
            module_path = ".".join(relative_source.with_suffix("").parts)
            cmd_list.extend(
                [
                    f"--cov={module_path}",
                    "--cov-report=term-missing",
                    "--cov-report=annotate",
                ],
            )
        cmd_list.append(str(path))
        cmd_str = " ".join(cmd_list)

        logger.info("[%s] Executing test runner: %s", prefix, cmd_str)

        result = subprocess.run(  # noqa: S603
            cmd_list,
            capture_output=True,
            text=True,
            check=False,
        )

        output_path = Path(f"unit-test-{test_stem}.txt")
        full_content = f"$ {cmd_str}\n\n{result.stdout}\n{result.stderr}"
        output_path.write_text(full_content, encoding="utf-8")

        logger.info(
            "[%s] Test runner finished with return code %d",
            prefix,
            result.returncode,
        )

        is_clean, pollution_errors = self.check_runtime_pollution(baseline, prefix)
        test_passed = result.returncode == 0
        overall_success = is_clean

        errors = []
        if not test_passed:
            errors.append(f"Test execution failed for {path}")
        errors.extend(pollution_errors)

        return overall_success, errors


def _collect_test_files(target_path: Path) -> list[Path]:
    """Collect valid test files matching test_*.py recursively using list.extend."""
    test_files: list[Path] = []
    if target_path.is_file():
        test_files.append(target_path)
    elif target_path.is_dir():
        test_files.extend(
            p
            for p in target_path.glob("**/test_*.py")
            if not any(part in IGNORED_DIRS for part in p.parts)
        )
    return test_files


def _run_static_checks(
    guard: WorkspaceGuard,
    test_files: list[Path],
) -> tuple[bool, list[dict[str, Any]]]:
    """Run static isolation checks across all collected test files."""
    all_passed = True
    results: list[dict[str, Any]] = []
    logger.info(
        "Running static test isolation checks on %d file(s)...",
        len(test_files),
    )
    for tf in test_files:
        is_isolated, errors = guard.check_static_isolation(tf, tf.name)
        status = "PASSED" if is_isolated else "WARNING"
        if not is_isolated:
            all_passed = False
        results.append(
            {
                "file": str(tf),
                "check": "Static Isolation",
                "status": status,
                "details": "; ".join(errors) if errors else "None",
            },
        )
    return all_passed, results


def _run_runtime_checks(
    guard: WorkspaceGuard,
    test_files: list[Path],
) -> tuple[bool, list[dict[str, Any]]]:
    """Run runtime test execution and pollution checks across test files."""
    all_passed = True
    results: list[dict[str, Any]] = []
    logger.info(
        "Running runtime test execution and workspace guard checks on %d file(s)...",
        len(test_files),
    )
    for tf in test_files:
        _, errors = guard.execute_test_and_guard(tf, tf.name)
        has_pollution = any("pollution" in err.lower() for err in errors)
        if has_pollution:
            status = "FAILED"
            all_passed = False
        elif errors:
            status = "WARNING"
        else:
            status = "PASSED"

        results.append(
            {
                "file": str(tf),
                "check": "Runtime Guard & Pytest",
                "status": status,
                "details": "; ".join(errors) if errors else "None",
            },
        )
    return all_passed, results


def _print_summary_table(results: list[dict[str, Any]]) -> None:
    """Print a clean synthetic summary table of all processed test files."""
    logger.info(
        "\n===================================================================================",
    )
    logger.info("%s", f"{'WORKSPACE GUARD EXECUTION SUMMARY':^83}")
    logger.info(
        "===================================================================================",
    )
    logger.info(
        "%s",
        f"{'Test File':<38} | {'Check Type':<22} | {'Status':<10} | {'Details':<10}",
    )
    logger.info(
        "-----------------------------------------------------------------------------------",
    )
    for res in results:
        logger.info(
            "%s",
            f"{res['file']:<38} | {res['check']:<22} | {res['status']:<10} | "
            f"{res['details']:<10}",
        )
    logger.info(
        "===================================================================================\n",
    )


def main() -> None:
    """CLI Gateway for workspace guard validation."""
    parser = argparse.ArgumentParser(
        description="Check test static isolation and runtime workspace pollution.",
    )
    parser.add_argument(
        "target",
        type=str,
        nargs="?",
        default="tests",
        help="Target test file or directory (default: tests)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--static",
        action="store_true",
        help="Perform only static AST isolation checks on test files.",
    )
    group.add_argument(
        "--runtime",
        action="store_true",
        help="Perform runtime snapshotting, execute pytest, and check pollution.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Perform both static isolation and runtime test execution guard checks.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    guard = WorkspaceGuard(project_path=Path.cwd())
    target_path = Path(args.target)

    run_static = args.static or args.all or (not args.static and not args.runtime)
    run_runtime = args.runtime or args.all

    test_files = _collect_test_files(target_path)
    if not test_files and target_path.exists():
        logger.error("No actionable test files found at target: %s", target_path)
        sys.exit(1)
    elif not target_path.exists():
        logger.error("Target path does not exist: %s", target_path)
        sys.exit(1)

    all_results: list[dict[str, Any]] = []
    success = True

    if run_static:
        _, static_results = _run_static_checks(guard, test_files)
        all_results.extend(static_results)

    if run_runtime:
        _, runtime_results = _run_runtime_checks(guard, test_files)
        all_results.extend(runtime_results)

    _print_summary_table(all_results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
