from alpha93.commons import type_checker

from terser.ast_compat import ast
from ._scope import ScopeResolver
from .ref import ModuleRef

if type_checker.TYPE_CHECKING:
    from typing import Any


def parse(source: str, path: str, *args, **kwargs):
    module: Any = ast.parse(source, path or "<unknown>", *args, **kwargs)
    module_ref = ModuleRef(module)
    ScopeResolver.module(module_ref)
    return module, module_ref
