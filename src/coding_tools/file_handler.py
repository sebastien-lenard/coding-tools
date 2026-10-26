# src/coding_tools/file_handler.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Manage paths for tool outputs, logs, and coverage.

Write files to disk (.coverage_annotations, .pytest_output, .pyright_output,
.ruff_output, .llm_output) relative to target project root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from coding_tools import my_logger

logger = my_logger.logger(__name__)

COVERAGE_ANNOTATIONS_DIR = ".coverage_annotations"
PYTEST_OUTPUT_DIR = ".pytest_output"
PYRIGHT_OUTPUT_DIR = ".pyright_output"
RUFF_OUTPUT_DIR = ".ruff_output"
LLM_OUTPUT_DIR = ".llm_output"

ALL_TOOL_OUTPUT_DIRS = {
    COVERAGE_ANNOTATIONS_DIR,
    PYTEST_OUTPUT_DIR,
    PYRIGHT_OUTPUT_DIR,
    RUFF_OUTPUT_DIR,
    LLM_OUTPUT_DIR,
}

WORKSPACE_ROOT_MARKERS = ["config", "docs", "src", "tests"]


@dataclass
class LLMOutputPathParameters:
    """Hold naming and timestamp fields for LLM output paths.

    Build nested paths under .llm_output dir.
    """

    llm_name: str
    start_date: str
    tool_name: str
    process_step: str
    target_file: str | Path
    status_label: str
    timestamp: int
    hhmiss: str
    project_root: Path | None = None


def files(path: Path | str, ext: str | None = ".py") -> list[Path]:
    func = f"{__name__}"
    path = Path(path).resolve()
    if not path.exists():
        msg = f"No {path}"
        raise FileNotFoundError(msg)

    files: list[Path] = []
    if path.is_file() and ext in (path.suffix, None):
        files.append(path)
        return files

    if not ext:
        files.extend(sorted(p for p in path.rglob("*") if p.is_file()))
    else:
        files.extend(sorted(path.rglob(ext)))

    this_ext = "" if not ext else f".{ext} "
    if not files:
        logger.warning(func, f"No file at {path}")
    else:
        logger.progress(func, f"Got {len(files)} {this_ext}at: {path}")

    return files


def get_project_root(path: str | Path) -> Path:
    """Deduct project root dir from path.

    Scan parents for workspace root markers (config, docs, src, tests).
    """
    path = Path(path).resolve()
    current = path if path.is_dir() else path.parent

    while current != current.parent:
        if any((current / marker).exists() for marker in WORKSPACE_ROOT_MARKERS):
            return current
        current = current.parent

    return path if path.is_dir() else path.parent.parent


def get_pyproject_path(path: str | Path) -> Path:
    """Get absolute path to pyproject.toml for project."""
    return get_project_root(path) / "pyproject.toml"


def get_conftest_path(path: str | Path) -> Path:
    """Get absolute path to tests/conftest.py for project."""
    return get_project_root(path) / "tests/conftest.py"


def ensure_directory(dir_path: str | Path) -> Path:
    """Create target dir if missing and return Path.

    Write to disk with parent creation enabled.
    """
    path = Path(dir_path)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception(path, "Failed to create target dir")
        raise
    return path


def get_tool_output_dir(target_file_path: str | Path, dir_name: str) -> Path:
    """Get tool output dir relative to project root.

    Write to disk.
    """
    proj_root = get_project_root(target_file_path)
    return ensure_directory(proj_root / dir_name)


def _get_stem_filename(test_file_path: str | Path) -> str:
    """Get file stem or name without duplicate extensions."""
    path = Path(test_file_path)
    return path.stem if path.suffix == ".py" else path.name


def get_pytest_log_path(test_file_path: str | Path) -> Path:
    """Get pytest log path under project root.

    Write to disk under .pytest_output.
    """
    base_dir = get_tool_output_dir(test_file_path, PYTEST_OUTPUT_DIR)
    stem = _get_stem_filename(test_file_path)
    return base_dir / f"unit-test-{stem}.txt"


def get_basedpyright_log_path(test_file_path: str | Path) -> Path:
    """Get based-pyright log path under project root.

    Write to disk under .pyright_output.
    """
    base_dir = get_tool_output_dir(test_file_path, PYRIGHT_OUTPUT_DIR)
    stem = _get_stem_filename(test_file_path)
    return base_dir / f"based-pyright-{stem}.txt"


def get_ruff_log_path(test_file_path: str | Path) -> Path:
    """Get ruff log path under project root.

    Write to disk under .ruff_output.
    """
    base_dir = get_tool_output_dir(test_file_path, RUFF_OUTPUT_DIR)
    stem = _get_stem_filename(test_file_path)
    return base_dir / f"ruff-{stem}.txt"


def pytest_cov_path(source_file_path: str | Path) -> Path | None:
    """Get coverage annotation path under project root.

    Write to disk under .coverage_annotations. Matches hash-prefixed filenames,
    yielding the most recent file.
    """
    base_dir = get_tool_output_dir(source_file_path, COVERAGE_ANNOTATIONS_DIR)
    target_name = Path(source_file_path).name
    matches = list(base_dir.glob(f"*_{target_name},cover"))
    if matches:
        cov_path = max(matches, key=lambda p: p.stat().st_mtime)
        logger.progress(None, f"Found pytest cov path {cov_path}")
        return cov_path
    logger.warning(None, f"No pytest cov file at {base_dir}")
    return None


def get_llm_output_path(params: LLMOutputPathParameters) -> Path:
    """Get nested path for LLM outputs.

    Write to disk under .llm_output.
    """
    proj_root = params.project_root or get_project_root(params.target_file)
    sanitized_llm_name = (
        params.llm_name.replace("/", "-").replace("\\", "-").replace(":", "-")
    )
    target_filename = Path(params.target_file).name
    filename = (
        f"{params.hhmiss}-{params.tool_name}-{params.process_step}-"
        f"{target_filename}-{params.status_label}-{params.timestamp}.json"
    )

    dir_path = proj_root / LLM_OUTPUT_DIR / sanitized_llm_name / params.start_date
    ensure_directory(dir_path)
    return dir_path / filename
