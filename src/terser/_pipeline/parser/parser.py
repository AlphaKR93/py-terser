from typing import TYPE_CHECKING

from terser.ast import DummySpec, ModuleRef, ast
from ._scope import ScopeResolver

if TYPE_CHECKING:
    from typing import Any

    from terser.ast.ref import ModuleSpec


def parse(source: str, spec: ModuleSpec | str, mode: str = "exec", **kwargs):
    if isinstance(spec, str):
        path = spec
        spec = DummySpec(spec)
    else:
        path = spec.path

    module: Any = ast.parse(source, path, mode, **kwargs)
    module_ref = ModuleRef(module, spec)
    ScopeResolver.module(module_ref)
    return module, module_ref
