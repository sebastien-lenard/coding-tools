# Coding Tools: Path Stamper

`path_stamper.py` is a simple utility designed to automatically inject a script's own file path as a comment at the very top of the file. 

### Why use it?
When copy-pasting multiple code files into Large Language Models (LLMs) for analysis, refactoring, or code generation, LLMs may lose track of which code belongs to which file. By "stamping" the path into the file header, the LLM instantly retains perfect file context without requiring you to type out filenames manually.

---

## Features

- **LLM-Ready Context:** Keeps file structures clear during copy-paste workflows.
- **Shebang & Encoding Aware:** Smart placement logic. Automatically inserts the path *after* existing shebang (`#!`) or encoding (`# -*- coding`) lines to keep your scripts executable.
- **Idempotent & Self-Refreshing:** Recognizes existing stamps to prevent duplicates, but automatically updates the header to the new path if the file is moved or renamed during project refactoring.

---

## Usage

Run the script by passing the target project directory absolute path as an argument.

### Stamp an Entire Directory
```bash
python path_stamper.py ./your_project_folder/
```

---

## Development & Testing

This project uses standard unit tests to ensure headers are injected correctly without breaking existing shebang lines.

### Run Unit Tests
```bash
python -m pytest tests
```
