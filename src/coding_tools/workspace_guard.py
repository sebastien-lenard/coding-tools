# src/coding_tools/workspace_guard.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Check static test isolation and runtime workspace pollution.

AST checks and pytest snapshot diffs. Writes pytest logs to disk.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, DirectoryPath

from coding_tools.file_handler import ALL_TOOL_OUTPUT_DIRS, get_pytest_log_path
from coding_tools.logger import get_project_logger, setup_logging

logger = get_project_logger(__name__)

IGNORED_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    *ALL_TOOL_OUTPUT_DIRS,
}
CHECKED_EXTENSIONS = {".py"}


class WorkspaceGuard(BaseModel):
    """Apply test file isolation and block workspace pollution.

    AST scan and file snapshot diffs during pytest runs.
    """

    project_path: DirectoryPath

    def check_static_isolation(
        self,
        test_file_path: str | Path,
        _prefix: str = "Guard",
    ) -> tuple[bool, list[str]]:
        """Scan test file AST to spot I/O without tmp_path fixture.

        False if test writes files or dirs without tmp_path or setup_mock_project.
        """
        path = Path(test_file_path)
        if not path.exists():
            logger.warning(
                path,
                "Test file not found. Static check skipped",
            )
            return True, []

        logger.progress(path, "Run static isolation check")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            logger.exception(path, "Failed AST scan (SyntaxError)")
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
            logger.warning(path, "Spot creation files (AST)")
        else:
            logger.progress(path, "Passed AST")

        return len(violations) == 0, violations

    def snapshot_workspace(self, _prefix: str = "Guard") -> set[Path]:
        """Get set of relative file paths across repo.

        Skips ignored dirs and non-python files.
        """
        logger.progress(None, "Snapshot repo", f"path={self.project_path}")
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
        logger.progress(
            None,
            f"Caught snapshot. {len(snapshot)} .py files",
        )
        return snapshot

    def check_runtime_pollution(
        self,
        baseline: set[Path],
        prefix: str = "Guard",
    ) -> tuple[bool, list[str]]:
        """Compare current workspace snapshot against baseline.

        False if new files appear.
        """
        logger.progress(None, "Check file creation (run)")
        current = self.snapshot_workspace(prefix)
        new_files = current - baseline

        violations: list[str] = []
        unauthorized_list: list[str] = []
        for f in new_files:
            unauthorized_list.append(str(f))
            violations.append(
                f"Spot file creation: {f}",
            )

        if violations:
            logger.warning(
                None,
                f"Spot file creation: {len(violations)} Files: {unauthorized_list}",
            )
        else:
            logger.progress(None, "Done. No file creation (runtime)")

        return len(violations) == 0, violations

    def execute_test_and_guard(
        self,
        test_file_path: str | Path,
        prefix: str = "Guard",
        *,
        run_coverage: bool = False,
        source_file_path: str | Path | None = None,
    ) -> tuple[bool, list[str]]:
        """Run pytest on test file and check workspace pollution.

        Saves output to log file. Uses uv run pytest with optional coverage.
        """
        baseline = self.snapshot_workspace(prefix)
        path = Path(test_file_path)

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
                    "--cov-branch",
                    "--cov-report=term-missing",
                    "--cov-report=annotate:.coverage_annotations",
                ],
            )
        cmd_list.append(str(path))
        cmd_str = " ".join(cmd_list)

        logger.progress(path, "run test_runner", cmd_str)

        result = subprocess.run(  # noqa: S603
            cmd_list,
            capture_output=True,
            text=True,
            check=False,
        )

        output_path = get_pytest_log_path(test_file_path)
        full_content = f"$ {cmd_str}\n\n{result.stdout}\n{result.stderr}"
        output_path.write_text(full_content, encoding="utf-8")

        logger.progress(
            path,
            "End Test runner",
            f"return_code={result.returncode}",
        )

        is_clean, pollution_errors = self.check_runtime_pollution(baseline, prefix)
        test_passed = result.returncode == 0
        overall_success = is_clean

        errors = []
        if not test_passed:
            errors.append(f"Test run failed for {path}")
        errors.extend(pollution_errors)

        return overall_success, errors


def _collect_test_files(target_path: Path) -> list[Path]:
    """Get test files matching test_*.py recursively.

    Skips ignored dirs.
    """
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
    """Run static isolation checks on test files.

    Return success bool and result dicts.
    """
    all_passed = True
    results: list[dict[str, Any]] = []
    logger.progress(
        None,
        "Run static isolation checks",
        f"files_count={len(test_files)}",
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
    """Run runtime test run and pollution checks on test files.

    Return success bool and result dicts.
    """
    all_passed = True
    results: list[dict[str, Any]] = []
    logger.progress(None, "Run runtime checks", f"files_count={len(test_files)}")
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


def main() -> None:
    """Run CLI gateway for workspace guard validation.

    Parse args for static, runtime, or all checks. Exit status based on success.
    """
    parser = argparse.ArgumentParser(
        description="Check tests don't create files in workspace (static and runtime)",
    )
    parser.add_argument(
        "target",
        type=str,
        nargs="?",
        default="tests",
        help="Target test file or dir (default: tests)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--static",
        action="store_true",
        help="Static AST checks only",
    )
    group.add_argument(
        "--runtime",
        action="store_true",
        help="Runtime pytest snapshot checks only",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="All checks",
    )
    args = parser.parse_args()

    setup_logging()

    guard = WorkspaceGuard(project_path=Path.cwd())
    target_path = Path(args.target)

    run_static = args.static or args.all or (not args.static and not args.runtime)
    run_runtime = args.runtime or args.all

    test_files = _collect_test_files(target_path)
    if not test_files and target_path.exists():
        logger.error(target_path, "Failed. No test files found")
        sys.exit(1)
    elif not target_path.exists():
        logger.error(target_path, "Failed. Target path doesn't exist")
        sys.exit(1)

    all_results: list[dict[str, Any]] = []
    success = True

    if run_static:
        _, static_results = _run_static_checks(guard, test_files)
        all_results.extend(static_results)

    if run_runtime:
        _, runtime_results = _run_runtime_checks(guard, test_files)
        all_results.extend(runtime_results)

    rows = [
        [res["file"], res["check"], res["status"], res["details"]]
        for res in all_results
    ]
    logger.summary_table(
        "Workspace Guard Summary:",
        ["Test File", "Check Type", "Status", "Details"],
        rows,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
