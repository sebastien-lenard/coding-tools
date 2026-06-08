# Coding Tools

A suite of utility workflows designed to manage file backups and automate context and license/copyright injection for local Python projects.

---

## 1. Workspace Stamper

`workspace-stamper` is an automated utility designed to inject relative file paths and standardized SPDX legal headers into Python source files. 

### Core Use Case
When copying and pasting multiple code files into Large Language Models (LLMs) for analysis, refactoring, or generation, LLMs frequently lose track of file boundaries and directory structures. Stamping the relative path into the file header ensures that the LLM retains perfect file context without requiring manual tagging.

Simultaneously, the utility injects standardized, compliant SPDX licensing blocks.


#### Why SPDX Headers Matter

Even when a repository includes a root `LICENSE` file, individual scripts can lose their licensing context if they are copied, shared, or reused independently.

Automating **SPDX header injection** ensures that:

* **Context is Retained:** Legal and copyright information remains permanently attached to the source code.
* **Automated Compliance:** Security and compliance scanners can instantly audit individual files without needing to parse the entire repository structure.


### Features
- **LLM-Ready Context:** Retains full file context during copy-paste workflows to LLM systems.
- **Shebang & Encoding Aware:** Automatically places metadata *after* any existing shebang (`#!`) or encoding declaration (`# -*- coding`) to preserve script execution syntax.
- **Idempotent Header Logic:** Detects existing stamps to prevent duplicates, but automatically updates the path header if a file is renamed or moved.
- **Resilient Licensing Assembly:**
  - If `LICENSE` is absent, the engine logs a warning but proceeds to stamp the `SPDX-License-Identifier` using the input ID.
  - If `NOTICE` is absent, the engine logs a warning but stamps the `SPDX-License-Identifier` and path, skipping only the copyright text.
  - **Sequential Header Upgrades:** Automatically appends the copyright line (`SPDX-FileCopyrightText`) if it is missing but a valid `NOTICE` exists, even if `SPDX-License-Identifier` is already present.
- **Mutual Deactivation Guard:** Exits cleanly with zero modifications if both path and license stamping options are bypassed.

### CLI Command Options
```bash
workspace-stamper target [OPTIONS]
```

#### Arguments
* **`target`** *(Positional, Required)*: The target system path. Can point to a single `.py` file or a directory.

#### Options
* **`--license-id`, `-l`** *(String)*: The targeted SPDX-License-Identifier (e.g., `MIT`, `Apache-2.0`). **Required** unless `--no-license` is explicitly passed. Must contain only alphanumeric characters, dashes (`-`), or dots (`.`).
* **`--project-dir`, `-p`** *(Directory Path)*: Root anchor directory housing `LICENSE` and `NOTICE` files.
  * **Optional** if `target` is a directory (defaults to `target`).
  * **Optional** if `target` is a file and `--no-license` is set (defaults to the file's parent folder).
  * **Required** if `target` is a file and license stamping is active.
* **`--no-path`** *(Flag)*: Bypasses or strips the top-of-file path comment.
* **`--no-license`** *(Flag)*: Bypasses or strips structural SPDX compliance headers.

---

## 2. Backup Untracked

`backup-untracked` copies untracked or ignored local development files (such as `.env` configurations or custom assets) out of your repository tree into an isolated backup folder.

### Core Use Case
Destructive Git cleanups (like `git clean -fdx` or hard resets) instantly delete uncommitted files that are omitted from your repository tree. Running this utility archives your local environment parameters prior to executing automated refactoring routines or switching branches.

### Features
- **Targeted Backup Parsing:** Uses a `.git_untracked_to_save` file placed in your project root to determine exactly what files or directories to copy.
- **Timestamped Isolation:** Groups files into isolated `backup_[project_name]_[timestamp]` directories to prevent older archives from being overwritten.
- **Idempotency Safety:** Only performs read-and-copy routines. It never modifies or deletes original source trees or previous backup structures.

#### Configuration Format (`.git_untracked_to_save`)
Place this configuration file at the root of your target project.
- **Line 1:** The absolute destination path where backups should be archived.
- **All subsequent lines:** Relative directory paths or specific file paths to copy.

*Example:*
```text
/Users/username/Desktop/MyBackups
.env
secrets/
```

---

## Installation & Setup

This project uses **uv** for fast and reliable Python package and dependency management.

### 1. Install `uv`

If you do not have `uv` installed, run the platform-specific installer:

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Synchronize the Environment

Navigate to the project root directory and synchronize the virtual environment to install dependencies and register CLI commands:
```bash
uv sync
```

---

## Usage Examples

Run the scripts directly using `uv run`.

### Running Workspace Stamper

**Example 1: Stamp a directory with MIT licensing (auto-detects project root paths)**
```bash
uv run workspace-stamper /path/to/target/project -l MIT
```

**Example 2: Stamp a single file (requires explicit project directory specification)**
```bash
uv run workspace-stamper /path/to/target/project/app.py -p /path/to/target/project -l Apache-2.0
```

**Example 3: Strip existing licensing and path stamps from a workspace**
```bash
uv run workspace-stamper /path/to/target/project --no-path --no-license
```

### Running Backup Untracked

Run directly from your active directory (defaults to checking for `.git_untracked_to_save` in the current folder):
```bash
uv run backup-untracked /path/to/your/project -v
```

---

## Automating Projects with Git Hooks

You can configure `backup-untracked` to run automatically before making a git commit.

### Installation Steps

1. **Locate your target project:** Identify the absolute path of the target repository (e.g., `/Users/username/projects/my-app`).
2. **Install or merge the pre-commit hook:**
   - **If `/path/to/target/.git/hooks/pre-commit` does not exist:** Copy the sample template:
     ```bash
     cp .githooks/pre-commit.sample /path/to/target/.git/hooks/pre-commit
     ```
   - **If the pre-commit file already exists:** Open your target project's `.git/hooks/pre-commit` and append the execution logic found in `.githooks/pre-commit.sample` to the bottom of the file.
3. **Configure Hook Paths:** Edit the active pre-commit hook file and set your absolute local system paths:
   ```bash
   CODING_TOOLS_DIR="/absolute/path/to/this/coding-tools-folder"
   TARGET_PROJECT_DIR="/absolute/path/to/your/target/project"
   ```
4. **Grant Executable Permissions:**
   ```bash
   chmod +x /path/to/target/.git/hooks/pre-commit
   ```

Now, whenever you invoke `git commit` within the target project, it will automatically query the environment within `coding-tools`, parse your project's local `.git_untracked_to_save` file, and create an isolated, timestamped archive before recording the commit.

---

## Testing & Quality Control

This project enforces complete type safety through `pydantic` validation boundaries and runs automated test suites through `pytest`.

Run the comprehensive test suites inside an isolated runtime managed automatically by `uv`:
```bash
uv run pytest
```