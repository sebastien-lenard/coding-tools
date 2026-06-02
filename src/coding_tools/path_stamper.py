import argparse
import re
import subprocess
import sys
from pathlib import Path


def generate_updated_content(content: str, rel_path_str: str) -> tuple[str, bool]:
    """
    Parses top-of-file comments to safely update or insert the script's relative path.
    Preserves shebangs and coding instructions perfectly.
    """
    lines = content.splitlines(keepends=True)
    expected_comment = f"# {rel_path_str}\n"

    if not lines:
        return expected_comment, True

    idx = 0
    if lines[idx].startswith("#!"):
        idx += 1

    if (
        idx < len(lines)
        and ("coding:" in lines[idx] or "coding=" in lines[idx])
        and lines[idx].startswith("#")
    ):
        idx += 1

    insertion_idx = idx
    comment_indices = []
    for i in range(insertion_idx, len(lines)):
        if lines[i].startswith("#"):
            comment_indices.append(i)
        else:
            break

    path_comment_pattern = re.compile(
        r"^#\s*([a-zA-Z]:[\\/])?([\w\-\.\\\/ ]+/)*[\w\-\.]+\.py\s*$"
    )

    existing_path_idx = None
    for c_idx in comment_indices:
        if path_comment_pattern.match(lines[c_idx].strip() + "\n"):
            existing_path_idx = c_idx
            break

    if existing_path_idx is not None:
        if lines[existing_path_idx] == expected_comment:
            return content, False
        lines[existing_path_idx] = expected_comment
        return "".join(lines), True
    else:
        lines.insert(insertion_idx, expected_comment)
        return "".join(lines), True


def scan_python_files(root_dir: Path) -> list[Path]:
    """Finds all project python files excluding environment assets."""
    all_py = root_dir.rglob("*.py")
    return [f for f in all_py if not any(part in f.parts for part in (".venv", "venv"))]


def verify_git_diff(root_dir: Path) -> tuple[bool, list[str]]:
    """
    Runs git diff strictly within the targeted project folder.
    Allows either a single path comment insertion OR a single path comment replacement.
    Returns (is_valid, error_messages_list).
    """
    errors = []
    try:
        # Pass "." explicitly to scope the diff strictly to the cwd (project root)
        result = subprocess.run(
            ["git", "diff", "-U0", "."],
            cwd=root_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return False, [f"Failed to execute git diff command: {e}"]

    if not result.stdout.strip():
        return True, []

    # Regex to ensure a hunk strictly contains a single added path comment
    hunk_header_pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
    # Matches both added (+) and deleted (-) lines that are pure path comments
    path_comment_pattern = re.compile(
        r"^[+-]\s*#\s*([\w\-\.\\\/ ]+/)*[\w\-\.]+\.py\s*$"
    )

    # Group the unified diff lines cleanly by file
    current_file = "Unknown File"
    file_hunks = {}

    for line in result.stdout.splitlines():
        if line.startswith("diff --git"):
            # Extract target file name path accurately from git headers
            match = re.search(r"b/(.+)$", line)
            current_file = match.group(1) if match else "Unknown File"
            file_hunks[current_file] = []
        elif current_file in file_hunks:
            if line.startswith("@@") or line.startswith("+") or line.startswith("-"):
                if not (line.startswith("---") or line.startswith("+++")):
                    file_hunks[current_file].append(line)

    # Process and evaluate each file's changes individually
    for filename, lines in file_hunks.items():
        if not lines:
            continue

        idx = 0
        while idx < len(lines):
            # 1. We expect a hunk header line
            if not hunk_header_pattern.match(lines[idx]):
                errors.append(
                    f"[{filename}] Unexpected git structural metadata line: "
                    "'{lines[idx]}'"
                )
                idx += 1
                continue

            # 2. Gather the content lines belonging to this specific header hunk
            hunk_content_lines = []
            idx += 1
            while idx < len(lines) and not hunk_header_pattern.match(lines[idx]):
                hunk_content_lines.append(lines[idx])
                idx += 1

            # --- VALIDATION LOGIC ---
            deletions = [l for l in hunk_content_lines if l.startswith("-")]
            additions = [l for l in hunk_content_lines if l.startswith("+")]

            # Scenario A: A pure new path comment insertion (0 deletions, 1 addition)
            if len(deletions) == 0 and len(additions) == 1:
                if not path_comment_pattern.match(additions[0]):
                    errors.append(
                        f"[{filename}] Added line is not a valid path comment: '{additions[0]}'"
                    )

            # Scenario B: An outdated path comment replacement (1 deletion, 1 addition)
            elif len(deletions) == 1 and len(additions) == 1:
                if not path_comment_pattern.match(
                    deletions[0]
                ) or not path_comment_pattern.match(additions[0]):
                    errors.append(
                        f"[{filename}] Modification is not a clean path comment replacement:\n"
                        f"  -> {deletions[0]}\n"
                        f"  -> {additions[0]}"
                    )

            # Scenario C: Anything else is unsafe (modifying actual code, multiple lines, etc.)
            else:
                errors.append(
                    f"[{filename}] Hunk contains unsafe code changes or unexpected line modifications:\n"
                    + "\n".join(f"  -> {l}" for l in hunk_content_lines)
                )

    return (len(errors) == 0), errors


def run_process(project_path: Path) -> bool:
    """
    Orchestrates validating the path, scanning targets,
    writing updated file contents, and verifying changes via Git.
    """
    project_path = project_path.resolve()
    if not project_path.exists() or not project_path.is_dir():
        print(
            f"Error: Path '{project_path}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        return False

    py_files = scan_python_files(project_path)
    if not py_files:
        print("No Python files found to process.")
        return True

    modified_count = 0
    for file_path in py_files:
        try:
            rel_path = file_path.relative_to(project_path)

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            new_content, is_modified = generate_updated_content(
                content, rel_path.as_posix()
            )

            if is_modified:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                modified_count += 1
                print(f"Updated header path: {rel_path.as_posix()}")

        except Exception as e:
            print(
                f"Failed to parse target script {file_path.name}: {e}", file=sys.stderr
            )

    print(f"Processed {len(py_files)} files. Modified {modified_count} targets.")

    # Run the Git validation step to safeguard your codebase
    print("Running Git diff structural verification safety check...")
    is_valid, git_errors = verify_git_diff(project_path)

    if not is_valid:
        print("\n" + "=" * 70, file=sys.stderr)
        print("CRITICAL ERROR: GIT DIFF SAFETY VALIDATION FAILED!", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(
            "The following unexpected changes were caught in your working tree:\n",
            file=sys.stderr,
        )
        for error in git_errors:
            print(f"  ❌ {error}", file=sys.stderr)
        print(
            "\n👉 Please review these files or discard unwanted modifications via 'git checkout'.",
            file=sys.stderr,
        )
        return False

    print("Success: Structural validation checks passed cleanly.")
    return True


def main() -> None:
    """CLI Entrypoint processing runtime arguments."""
    parser = argparse.ArgumentParser(
        description="Automate file path headers for Python script targets safely."
    )
    parser.add_argument(
        "project_dir", type=str, help="Root folder system path of the target code base."
    )
    args = parser.parse_args()

    success = run_process(Path(args.project_dir))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
