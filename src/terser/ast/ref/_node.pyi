import ast
from abc import ABC
from ast import AST
from typing import overload, ClassVar

from . import ModuleRef
from terser._pipeline.parser.ref._scoped import ScopedNode


type Invokable = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
type Comprehension = ast.GeneratorExp | ast.ListComp | ast.SetComp | ast.DictComp
type ContainsScope = ast.Module | ast.ClassDef | Invokable | Comprehension


class NodeRef[T: AST](ABC):
    _klass: ClassVar[dict[type[ast.AST], type[NodeRef]]]
    _ast: T
    _parent: AST

    namespace: ContainsScope

    @classmethod
    def new(cls, node: T, parent: AST) -> NodeRef[T]: ...

    def __init__(self, node: T, parent: AST) -> None: ...
    def _resolve_all(self) -> None: ...


@overload
def ref(node: ast.Module) -> ModuleRef: ...
@overload
def ref[T: ContainsScope](node: T) -> ScopedNode[T]: ...
@overload
def ref[T: AST](node: T) -> NodeRef[T]: ...
