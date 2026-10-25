from __future__ import annotations

from pathlib import Path

from coding_tools.logger import get_project_logger

logger = get_project_logger(__name__)


def read_lines(path: Path | str) -> list[str]:
    path = Path(path)

    if not path.exists() or not path.exists():
        logger.warning(None, f"No {path}")
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.exception(None, f"Failed to read {path}")
        return []
    return lines
