from ._constants import hoist_literals
from ._globals import mangle_globals
from ._locals import mangle_locals

__all__ = (
    "hoist_literals",
    "mangle_locals",
    "mangle_globals",
)
