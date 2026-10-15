# bundle_sources.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Bundle project source files into a single text file, stripping redundant headers."""

import os
import re
import subprocess
from pathlib import Path

# Force Python into UTF-8 mode on Windows
os.environ["PYTHONUTF8"] = "1"


def bundle_sources(output_path: Path) -> None:
    """Run files-to-prompt commands, strip redundant headers, and save output."""
    cmd1 = [
        "uvx",
        "files-to-prompt",
        "src",
        "--ignore",
        "__pycache__",
        "--ignore",
        ".git",
        "--ignore",
        "venv",
    ]
    result1 = subprocess.run(  # noqa: S603
        cmd1,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )

    cmd2 = [
        "uvx",
        "files-to-prompt",
        ".",
        "--include-hidden",
        "-e",
        "example",
        "-e",
        "toml",
    ]
    result2 = subprocess.run(  # noqa: S603
        cmd2,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )

    combined_content = result1.stdout + result2.stdout

    # Matches the filepath line and the '---' separator line at the start of each block
    pattern = r"^[^\r\n]+\r?\n---\r?\n"
    cleaned_content = re.sub(pattern, "", combined_content, flags=re.MULTILINE)

    output_path.write_text(cleaned_content, encoding="utf-8")
    print(f"Codebase successfully bundled into {output_path}")  # noqa: T201


if __name__ == "__main__":
    target_file = Path("eventus-publicus.txt")
    bundle_sources(target_file)
