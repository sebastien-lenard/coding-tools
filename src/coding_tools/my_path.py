# src/coding_tools/my_path.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Manage paths for tools, logs, and coverage.

Write files to disk (.coverage_annotations, .pytest_output, .pyright_output,
.ruff_output, .llm_output) under target project root. Path logic and checks.
"""

from __future__ import annotations

import re
from pathlib import Path

from coding_tools import my_io, my_logger, my_string, my_time

logger = my_logger.logger(__name__)

CONFTEST_FILE_PATH = "tests/conftest.py"
COVERAGE_ANNOTATIONS_DIR = ".coverage_annotations"
INIT_FILE_PATH = "__init__.py"
LLM_LOG_DIR = ".llm_logs"
PYRIGHT_OUTPUT_DIR = ".pyright_output"
PYTEST_OUTPUT_DIR = ".pytest_output"
RUFF_OUTPUT_DIR = ".ruff_output"
SRC_DIR = Path("src")
TEST_FILENAME_PATTERN = "test_*.py"
UNIT_TEST_DIR = Path("tests/unit")
UNIT_TEST_DEFAULT_TXT = "def test_dummy() -> None:\n    assert 1 == 1\n"


ALL_TOOL_OUTPUT_DIRS = {
    COVERAGE_ANNOTATIONS_DIR,
    PYTEST_OUTPUT_DIR,
    PYRIGHT_OUTPUT_DIR,
    RUFF_OUTPUT_DIR,
    LLM_LOG_DIR,
}

WORKSPACE_ROOT_MARKERS = ["config", "docs", "src", "tests"]


def clean(txt: str) -> str:
    """Clean text to fit file or folder name.

    Strip bad symbols, slugify spaces, lowercase.
    """
    txt = re.sub(r"[^\w\s\.-]", "", Path(txt).stem)
    return re.sub(r"[-\s_]+", "-", txt).strip("-.").lower()


def files(path: list[Path | str] | Path | str, ext: str | None = ".py") -> list[Path]:
    """Get list of match file paths.

    Read disk, raise FileNotFoundError if no path. Log count or warning.
    """
    func = f"{__name__}"

    path_list = (
        [Path(path)] if isinstance(path, (Path, str)) else [Path(p) for p in path]
    )

    ext = f"*.{ext}" if ext and not ext.startswith(".") else ext
    pattern = my_string.my_str(ext)
    pattern = f"{pattern}" if pattern else f"*{pattern}"

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
            out_files.extend(sorted(p for p in res_path.rglob(pattern) if p.is_file()))
        else:
            out_files.extend(sorted(res_path.rglob(pattern)))

    this_ext = "" if not ext else f".{ext} "
    if not out_files:
        logger.warning(func, f"No file at {path}")
    else:
        logger.progress(func, f"Got {len(out_files)} {this_ext} at: {path}")

    return sorted(set(out_files))


def prj_root(path: str | Path) -> Path:
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
    return prj_root(path) / "pyproject.toml"


def conftest_path(path: Path | str) -> Path:
    """Get absolute path to tests/conftest.py for project."""
    return prj_root(path) / CONFTEST_FILE_PATH


def ensure_directory(dir_path: str | Path) -> Path:
    """Create target dir if missing and return Path.

    Write to disk with parent creation enabled. Raise OSError on fail.
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
    proj_root = prj_root(target_file_path)
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


def is_unit_test(path: Path | str) -> bool:
    """Check if path is a unit test script.

    Match UNIT_TEST_DIR and test pattern.
    """
    p = Path(path)
    try:
        p.relative_to(UNIT_TEST_DIR)
    except ValueError:
        return False
    return p.match(TEST_FILENAME_PATTERN)


def latest_path(my_dir: Path, txt: str) -> Path:
    """Get latest file match by mtime in dir.

    Raise FileNotFoundError if dir missing or no match.
    """
    if not my_dir.is_dir():
        msg = f"No dir {my_dir}"
        raise FileNotFoundError(msg)
    matches = list(my_dir.glob(txt))
    if matches:
        return max(matches, key=lambda p: p.stat().st_mtime)
    msg = f"No file with {txt} at {my_dir}"
    raise FileNotFoundError(msg)


def pytest_cov_dir(source_file_path: str | Path) -> Path:
    """Get coverage annotations directory for source file."""
    return get_tool_output_dir(source_file_path, COVERAGE_ANNOTATIONS_DIR)


def pytest_cov_path(source_file_path: str | Path) -> Path:
    """Get coverage annotation path under project root.

    Write to disk under .coverage_annotations. Match hash prefix, yield
    most recent file. Raise FileNotFoundError.
    """
    base_dir = pytest_cov_dir(source_file_path)
    pattern = f"*_{Path(source_file_path).name},cover"
    return latest_path(base_dir, pattern)


def llm_log_path(
    func: str,
    llm: str,
    input_path: Path | str | None = None,
    root: Path | str | None = None,
) -> Path:
    """Get nested path for LLM request and response contents.

    Write to disk under .llm_logs. Raise ValueError if root is none.
    """
    func = "llm_log_path"
    root = root or (prj_root(input_path) if input_path else None)
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
    """Get module dotted path from source file path.

    Raise ValueError if src folder missing.
    """
    src_file_path = Path(str(src_file_path)).resolve()
    try:
        relative_src = src_file_path.relative_to(
            prj_root(src_file_path) / SRC_DIR,
        )
    except ValueError:
        logger.exception(None, f"No src module at {src_file_path}")
        raise

    if relative_src.name == INIT_FILE_PATH:
        relative_src = relative_src.parent

    if not relative_src.parts or relative_src == Path():
        return prj_root(src_file_path).name

    return ".".join(relative_src.with_suffix("").parts)


def src_path(test_file_path: Path | str) -> Path:
    """Map unit test path to source file path.

    E.g. 'tests/unit/xx/test_yy.py' to 'src/xx/yy.py'. Raise FileNotFoundError.
    """
    path = Path(test_file_path)
    name = path.name.removeprefix("test_")
    root = prj_root(path)

    match = next((p for p in (root / SRC_DIR).rglob(name) if p.is_file()), None)
    if not match:
        msg = f"No source file for {path}"
        raise FileNotFoundError(msg)

    logger.progress(None, f"Mapped {path} to {match}")
    return match


def to_path_list(
    paths: list[Path] | list[str] | Path | str | None,
) -> list[Path]:
    """Convert various path inputs to list of Path objects."""
    if paths is None:
        return []
    if isinstance(paths, (Path, str)):
        return [Path(paths)]
    return [Path(p) for p in paths]


def unit_test_path(
    src_file_path: list[Path] | list[str] | Path | str | None,
) -> list[Path]:
    """Map source file paths to unit test paths.

    E.g. 'src/xx/yy.py' to 'tests/unit/xx/test_yy.py'. Create test file stub
    if missing. Raise ValueError if src folder missing.
    """
    path_list = to_path_list(src_file_path)
    out_paths: list[Path] = []

    for item in path_list:
        res_item = item.resolve()
        try:
            rel_src = res_item.relative_to(
                prj_root(res_item) / SRC_DIR,
            )
        except ValueError:
            logger.exception(None, f"No src folder in {res_item}")
            raise
        rel_src = rel_src.relative_to(rel_src.parts[0])
        test_filename = f"test_{rel_src.name}"

        test_path = UNIT_TEST_DIR / rel_src.parent / test_filename
        test_path.parent.mkdir(parents=True, exist_ok=True)
        if not test_path.exists() or test_path.stat().st_size == 0:
            my_io.write_txt(UNIT_TEST_DEFAULT_TXT, test_path)
            logger.progress(None, f"Created test file {test_path}")

        out_paths.append(test_path)

    logger.progress(
        None,
        f"Mapped {len(out_paths)} source file(s) to unit test path(s)",
    )
    return sorted(out_paths)
