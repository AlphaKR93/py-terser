from typing import TYPE_CHECKING

from terser.ast_compat import ast
from ._scope import ScopeResolver
from .ref import ModuleRef, spec as __spec

if TYPE_CHECKING:
    from typing import Any


def parse(source: str, spec: __spec.ModuleSpec | str, mode: str, **kwargs):
    if isinstance(spec, str):
        path = spec
        spec = __spec.DummySpec(spec)
    else:
        path = spec.path

    module: Any = ast.parse(source, path, mode, **kwargs)
    module_ref = ModuleRef(module, spec)
    ScopeResolver.module(module_ref)
    return module, module_ref
