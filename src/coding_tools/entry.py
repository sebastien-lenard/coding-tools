# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0

"""Route CLI args to lead main.

Needs sys.argv access.
"""

from __future__ import annotations

import sys

from coding_tools import lead


def fix_lint() -> None:
    """Run fix-lint task via lead main.

    Set up sys.argv, call lead.main(). Needs sys.argv access.
    """
    sys.argv.insert(1, "fix-lint")
    lead.main()


def fix_type() -> None:
    sys.argv.insert(1, "fix-type")
    lead.main()


def pen_docstring() -> None:
    """Run pen-docstring task via lead main.

    Set up sys.argv, call lead.main(). Needs sys.argv access.
    """
    sys.argv.insert(1, "pen-docstring")
    lead.main()


def pen_test() -> None:
    sys.argv.insert(1, "pen-test")
    sys.argv.insert(2, "--test")
    lead.main()
