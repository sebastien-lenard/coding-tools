# src/coding_tools/file_handler.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Manage paths for tool outputs, logs, and coverage.

Write files to disk (.coverage_annotations, .pytest_output, .pyright_output,
.ruff_output, .llm_output) relative to target project root.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from coding_tools import my_io, my_logger, my_time

logger = my_logger.logger(__name__)

COVERAGE_ANNOTATIONS_DIR = ".coverage_annotations"
PYTEST_OUTPUT_DIR = ".pytest_output"
PYRIGHT_OUTPUT_DIR = ".pyright_output"
RUFF_OUTPUT_DIR = ".ruff_output"
LLM_LOG_DIR = ".llm_logs"

ALL_TOOL_OUTPUT_DIRS = {
    COVERAGE_ANNOTATIONS_DIR,
    PYTEST_OUTPUT_DIR,
    PYRIGHT_OUTPUT_DIR,
    RUFF_OUTPUT_DIR,
    LLM_LOG_DIR,
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


def clean(txt: str) -> str:
    """Clean text to be part of a file or folder name."""
    txt = re.sub(r"[^\w\s\.-]", "", Path(txt).stem)
    return re.sub(r"[-\s_]+", "-", txt).strip("-.").lower()


def files(path: list[Path | str] | Path | str, ext: str | None = ".py") -> list[Path]:
    func = f"{__name__}"

    path_list = (
        [Path(path)] if isinstance(path, (Path, str)) else [Path(p) for p in path]
    )
    out_files: list[Path] = []

    for item in path_list:
        res_path = item.resolve()
        if not res_path.exists():
            msg = f"No {res_path}"
            raise FileNotFoundError(msg)

        if res_path.is_file() and ext in (res_path.suffix, None):
            out_files.append(res_path)
            continue

        if not ext:
            out_files.extend(sorted(p for p in res_path.rglob("*") if p.is_file()))
        else:
            out_files.extend(sorted(res_path.rglob(ext)))

    this_ext = "" if not ext else f".{ext} "
    if not out_files:
        logger.warning(func, f"No file at {path}")
    else:
        logger.progress(func, f"Got {len(out_files)} {this_ext}at: {path}")

    return sorted(set(out_files))


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


def get_pytest_log_path(src_file_path: str | Path) -> Path:
    """Get pytest log path under project root.

    Write to disk under .pytest_output.
    """
    base_dir = get_tool_output_dir(src_file_path, PYTEST_OUTPUT_DIR)
    stem = _get_stem_filename(src_file_path)
    return base_dir / f"unit-test-test-{stem}.txt"


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


def latest_path(dir: Path, txt: str) -> Path | None:
    if not dir.is_dir():
        msg = f"No dir {dir}"
        raise FileNotFoundError(msg)
    matches = list(dir.glob(txt))
    if matches:
        return max(matches, key=lambda p: p.stat().st_mtime)
    msg = f"No file with {txt} at {dir}"
    raise FileNotFoundError(msg)


def pytest_cov_path(source_file_path: str | Path) -> Path | None:
    """Get coverage annotation path under project root.

    Write to disk under .coverage_annotations. Matches hash-prefixed filenames,
    yielding the most recent file.
    """
    base_dir = get_tool_output_dir(source_file_path, COVERAGE_ANNOTATIONS_DIR)
    pattern = f"*_{Path(source_file_path).name},cover"
    try:
        return latest_path(base_dir, pattern)
    except FileNotFoundError:
        logger.warning(None, f"No pytest cov {pattern} file at {base_dir}")
        return None


def llm_log_path(
    func: str,
    llm: str,
    input_path: Path | str | None = None,
    root: Path | str | None = None,
) -> Path:
    """Get nested path for LLM request/response contents.

    Write to disk under .llm_logs.
    """
    func = "llm_log_path"
    root = root or (get_project_root(input_path) if input_path else None)
    if root is None:
        msg = f"No target root given ({func})"
        raise ValueError(msg)
    timestamp, day, time = my_time.now()
    filename = (
        f"{time}_{func}"
        f"{'_' + (Path(input_path).name if input_path else '') + '_'}{timestamp}.md"
    )

    dir_path = Path(root) / LLM_LOG_DIR / clean(llm) / day
    ensure_directory(dir_path)
    return dir_path / filename


def module_path(src_file_path: Path | str | None) -> str | None:
    src_file_path = Path(str(src_file_path)).resolve()
    try:
        relative_src = src_file_path.relative_to(
            get_project_root(src_file_path) / "src",
        )
    except ValueError:
        logger.exception(None, f"No src module at {src_file_path}")
        raise

    return ".".join(relative_src.with_suffix("").parts)


def src_path(test_file_path: Path | str) -> Path:
    """Map a unit test path to source file path.

    E.g. 'tests/unit/xx/test_yy.py' to 'src/xx/yy.py'.
    """
    path = Path(str(test_file_path))
    try:
        relative_test = path.relative_to(Path("tests/unit"))
    except ValueError:
        logger.exception(None, f"No tests/unit base at {path}")
        raise

    src_filename = relative_test.name.removeprefix("test_")
    src_path = Path("src") / relative_test.parent / src_filename
    logger.progress(None, f"Mapped {path} to {src_path}")
    return src_path


def to_path_list(
    paths: list[Path] | list[str] | Path | str | None,
) -> list[Path]:
    if paths is None:
        return []
    if isinstance(paths, (Path, str)):
        return [Path(paths)]
    return [Path(p) for p in paths]


def unit_test_path(src_file_path: Path | str | None) -> Path:
    """Map a source file path to unit test path. Create test file stub if missing.

    E.g. 'src/xx/yy.py' to 'tests/unit/xx/test_yy.py'.
    """
    src_file_path = Path(str(src_file_path)).resolve()
    try:
        relative_src = src_file_path.relative_to(
            get_project_root(src_file_path) / "src",
        )
    except ValueError:
        logger.exception(None, f"No src folder in {src_file_path}")
        raise
    relative_src = relative_src.relative_to(relative_src.parts[0])
    test_filename = f"test_{relative_src.name}"

    test_path = Path("tests/unit") / relative_src.parent / test_filename
    test_path.parent.mkdir(parents=True, exist_ok=True)
    if not test_path.exists() or test_path.stat().st_size == 0:
        my_io.write_txt(
            ("test_dummy() -> None:\n    assert 1 == 1\n"),
            test_path,
        )
        logger.progress(None, f"Created test file {test_path}")

    return Path("tests/unit") / relative_src.parent / test_filename
