# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Entry point wrapper for lead tool dispatch.

Routes CLI args to lead main. Needs sys.argv access.
"""

from __future__ import annotations

import sys

from coding_tools import lead


def pen_docstring() -> None:
    """Run pen-docstring task via lead main.

    Inserts arg into sys.argv. Calls lead.main().
    """
    sys.argv.insert(1, "pen-docstring")
    lead.main()


def fix_lint() -> None:
    """Run fix-lint task via lead main.

    Inserts arg into sys.argv. Calls lead.main().
    """
    sys.argv.insert(1, "fix-lint")
    lead.main()
