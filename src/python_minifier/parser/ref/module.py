from typing import final

from ..._ast import ast
from ._scoped import ScopedNode


@final
class _Root(ast.AST):
    def __repr__(self):
        return "Root()"


@final
class ModuleRef(ScopedNode[ast.Module]):
    tainted: bool
    preserved: set[str]

    def __init__(self, module: ast.Module):
        super().__init__(module, None)  # type: ignore[invalid-type]
        self._resolve_all()

        self.tainted = False
        self.preserved = set()

    @property
    def _parent(self):
        raise ValueError("Root node cannot have parent")
