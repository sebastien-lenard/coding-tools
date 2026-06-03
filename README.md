# Coding Tools

A suite of utility workflows designed to safely manage file back-ups and automate context injection for local Python projects.

---

## 1. Path Stamper

`path-stamper` is a utility designed to automatically inject a script's own relative file path as a comment at the very top of the file. 

### Why use it?
When copy-pasting multiple code files into Large Language Models (LLMs) for analysis, refactoring, or generation, LLMs frequently lose track of which block of code belongs to which file. By "stamping" the path into the file header, the LLM instantly retains perfect file context without requiring you to manually type out filenames.

### Features
- **LLM-Ready Context:** Keeps file hierarchies crystal clear during copy-paste workflows.
- **Shebang & Encoding Aware:** Smart placement logic automatically inserts the path *after* an existing shebang (`#!`) or encoding declaration (`# -*- coding`) to keep your scripts fully executable.
- **Idempotent & Self-Refreshing:** Recognizes existing stamps to prevent duplicates, but automatically updates the header if a file is moved or renamed.
- **Git Safety Verification:** Automatically cross-checks your working tree post-run. If it detects any edits beyond pure path comments, it fails safely and alerts you.

---

## 2. Backup Untracked

`backup-untracked` safely copies uncommitted or ignored local files (such as `.env` keys, configuration profiles, or custom local assets) out of your project tree into an external backup folder.

### Why use it?
Destructive Git commands (like `git clean -fdx` or hard resets) can instantly vaporize uncommitted files that aren't tracked by repository history. Running this prior to aggressive automated refactoring or branch shifts ensures your local environment state is securely archived.

### Features
- **Targeted Backups:** Uses a `.git_untracked_to_save` file placed in your project root to determine exactly what to save.
- **Timestamped Isolation:** Groups your files into isolated `backup_[project_name]_[timestamp]` directories to prevent older backups from being overwritten.
- **Idempotent Safety:** Strictly reads and copies files—it will never delete or alter your original source tree or historical backup assets.

#### Configuration Format (`.git_untracked_to_save`)
Create this file in your target project directory. The first line **must** be the absolute destination where backups should be saved. All subsequent lines are the relative paths within the project to copy:
```text
/Users/username/Desktop/MyBackups
.env
secrets/

```

---

## Installation & Setup

This project uses **uv** for blazing fast, reliable Python package and environment management.

### 1. Install `uv`

If you don't have `uv` installed, run the platform-specific installer:

**macOS/Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"

```

### 2. Synchronize the Environment

Clone the project, navigate to the root directory, and run the synchronization command to automatically install Python 3.12.9, pull your dependencies, and register the global CLI commands:

```bash
uv sync

```

---

## Usage

Thanks to the project's `pyproject.toml` configurations, you don't need to invoke raw Python script paths anymore. Run them directly using `uv run`.

### Running Path Stamper

Pass the target folder directory as an argument:

```bash
uv run path-stamper /path/to/your/project/directory/to/path/stamp

```

### Running Backup Untracked

Run it directly from your active directory (defaults to looking for `.git_untracked_to_save` in `.`). Add `-v` or `--verbose` to see successful copy outputs:

```bash
uv run backup-untracked /path/to/your/project/directory/to/save/untracked -v

```

---

## Automating External Projects with Git Hooks

You can use `backup-untracked` to automatically protect *any* separate development project on your local machine before making a git commit. 

To achieve this, you must copy the shared hook template into the target project's internal Git lifecycle folder and customize its file system paths.

### Step-by-Step Installation

1. **Locate your target project:** Identify the absolute path of the project you want to back up (e.g., `/Users/name/projects/my-app`).

2. **Install or merge the hook:** Check if your target project already has an active pre-commit hook at `/path/to/your/target/project/.git/hooks/pre-commit`.
   
   * **If the file does NOT exist:** Copy the sample template file into your target project's Git lifecycle folder, removing the `.sample` extension:
     ```bash
     cp .githooks/pre-commit.sample /path/to/your/target/project/.git/hooks/pre-commit
     ```
   * **If the file ALREADY exists:** Open your target project's existing `.git/hooks/pre-commit` file and append the core execution logic from `.githooks/pre-commit.sample` to the bottom of the file.

3. **Configure the paths:** Open that new `.git/hooks/pre-commit` file in an editor and update the configuration lines with your absolute system paths:
```bash
CODING_TOOLS_DIR="/absolute/path/to/this/coding-tools-folder"
TARGET_PROJECT_DIR="/absolute/path/to/your/target/project"

```


4. **Make the hook executable:** If you are on macOS or Linux, grant Git permission to execute the script by running:
```bash
chmod +x /path/to/your/target/project/.git/hooks/pre-commit

```

Now, whenever you type `git commit` inside your target project, it will automatically look up the environment inside `coding-tools`, read your target project's `.git_untracked_to_save` file, and safely execute the backup before saving your code!

---

## Development & Testing

This project targets strict typing rules via Pydantic and isolates its test suites using `pytest`.

### Run Unit Tests

Run your tests inside an isolated runtime managed automatically by `uv`:

```bash
uv run pytest

```

