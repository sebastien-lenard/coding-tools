# src/coding_tools/my_import.py  # noqa: ERA001
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
"""Route LLM calls and map tools.

Dynamic import of mods by name. Catch load and OS faults. Log and raise.
"""

import importlib
import types

from coding_tools import my_logger

logger = my_logger.logger(__name__)


def import_module(mod_name: str) -> types.ModuleType:
    """Load mod by name safely.

    Catch load and OS faults via ImportError and OSError, log via logger, and raise.
    Uses importlib.import_module.
    """
    func = __name__
    try:
        return importlib.import_module(mod_name)
    except (ImportError, OSError):
        logger.exception(func, f"Import fail: {mod_name}")
        logger.end(func)
        raise
