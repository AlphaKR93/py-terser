"""
This package transforms python source code strings or ast.Module Nodes into
a 'minified' representation of the same source code.

"""

from ._minify import unparse
from .terser import minify, minify_project

version = "0.1.0"

__all__ = (
    "unparse",
    "minify",
    "minify_project",
)
