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
