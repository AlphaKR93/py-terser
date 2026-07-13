import ast
from alpha93.commons import type_checker

if type_checker.TYPE_CHECKING:
    from ast import AST
    from typing import Final


_FIELD = "__AST_NodeRef__ref__"


class NodeRef[T: AST]:
    _ast: Final[T]
    _parent: AST

    def __init__(self, node: T, parent: AST):
        setattr(node, _FIELD, self)

        self._ast = node
        if parent:  # INTENDED: for ModuleRef
            self._parent = parent

    def _resolve_all(self):
        for node in ast.iter_child_nodes(self._ast):
            NodeRef(node, self._ast)._resolve_all()

    def __repr__(self):
        r = {i: f"{j.__class__.__name__}(...)" if isinstance(j, ast.AST) else repr(j) for i, j in self.__dict__.items()}
        return f"{self.__class__.__name__}({', '.join([f"{k}={v}" for k, v in r.items()])})"


ref = lambda node: getattr(node, _FIELD)
