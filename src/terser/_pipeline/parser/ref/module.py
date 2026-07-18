from typing import TYPE_CHECKING, final

from terser.ast_compat import ast
from ._scoped import ScopedNode

if TYPE_CHECKING:
    from .namespace import Namespace


@final
class _Root(ast.AST):
    def __repr__(self):
        return "Root()"


@final
class ModuleRef(ScopedNode[ast.Module]):
    tainted: bool
    preserved: set[str]
    imports: dict[str, ast.AST]

    name: Namespace

    def __init__(self, module: ast.Module, name: Namespace):
        self.tainted = False
        self.preserved = set()
        self.name = name

        super().__init__(module, None)  # type: ignore[invalid-type]
        self._resolve_all()

    @property
    def _parent(self):
        raise ValueError("Root node cannot have parent")

ScopedNode._klass[ast.Module] = ModuleRef
