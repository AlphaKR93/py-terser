from alpha93.commons import type_checker

from terser.ast_compat import ast
from ._node import NodeRef

if type_checker.TYPE_CHECKING:
    from typing import Final, TypeGuard

    from terser._pipeline.linker.binder.binding import Binding
    from ._node import ContainsScope


SCOPED_T: Final[tuple[type[ContainsScope], ...]] = (
    ast.FunctionDef,
    ast.Lambda,
    ast.ClassDef,
    ast.Module,
    ast.GeneratorExp,
    ast.SetComp,
    ast.DictComp,
    ast.ListComp,
    ast.AsyncFunctionDef,
)

class ScopedNode[T: ContainsScope](NodeRef[T]):
    bindings: list[Binding]
    globals: set[str]
    nonlocals: set[str]

    def __init__(self, node: T, parent: ast.AST):
        super().__init__(node, parent)
        self.bindings = []
        self.globals = set()
        self.nonlocals = set()

for k in SCOPED_T:
    NodeRef._klass[k] = ScopedNode

def is_scoped(node: ast.AST) -> TypeGuard[ContainsScope]:
    return isinstance(node, SCOPED_T)
