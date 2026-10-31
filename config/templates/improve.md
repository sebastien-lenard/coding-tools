<!-- config/templates/improve.md -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
--- To do ---
{msg}
{python_version}
{skill}
--- End of To do --
--- Tips ---
{tips}
--- End of Tips ---
--- Files for tip context, don't edit ---
{context_files}
{conftest}
--- End of Files for context ---
--- Files to edit ---
Each file contains header comments with the file path relative to the project.
{files_to_edit}
Entire file content given.
--- End of Files to edit ---
--- Response expected ---
Give:
- a message
- the fully updated file with header comments if only one file (edited_files)
- or the concatenation of fully updated files with header comments if several files (edited_files).