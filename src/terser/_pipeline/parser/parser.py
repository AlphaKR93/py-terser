from typing import TYPE_CHECKING

from terser.ast_compat import ast
from ._scope import ScopeResolver
from .ref import ModuleRef

if TYPE_CHECKING:
    from typing import Any


def parse(source: str, namespace, path: str, *args, **kwargs):
    module: Any = ast.parse(source, path or "<unknown>", *args, **kwargs)
    module_ref = ModuleRef(module, namespace)
    ScopeResolver.module(module_ref)
    return module, module_ref
