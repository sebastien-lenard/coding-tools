# src/coding_tools/llm_router.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
import importlib
import types

from coding_tools import my_logger

logger = my_logger.logger(__name__)


def import_module(mod_name: str) -> types.ModuleType:
    func = __name__
    try:
        return importlib.import_module(mod_name)
    except (ImportError, OSError):
        logger.exception(func, f"Import fail: {mod_name}")
        logger.end(func)
        raise
