from .global_mangle import mangle_globals
from .renamer import mangle_locals

__all__ = (
    "mangle_locals",
    "mangle_globals",
)
