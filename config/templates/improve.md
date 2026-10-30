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
Content for each file starts with a comment giving the path relative to the project.
{files_to_edit}
Entire file content given.
--- End of Files to edit ---
--- Response expected ---
Give:
- a message
- the fully updated file if only one file (edited_files)
- or the concatenation of fully updated files if several files (edited_files).