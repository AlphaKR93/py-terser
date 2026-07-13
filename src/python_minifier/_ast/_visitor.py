from abc import ABC
from typing import override

from alpha93.commons import type_checker

from . import ast

if type_checker.TYPE_CHECKING:
    from collections.abc import Callable


class NodeVisitor(ast.NodeVisitor, ABC):
    def __visitor(self, name: str) -> Callable[[ast.AST], ast.AST]:
        return getattr(self, f"visit_{name}", self.generic_visit)

    @override
    def visit(self, node: ast.AST):
        """Visit a node."""
        return self.__visitor(node.__class__.__name__)(node)

    @override
    def generic_visit(self, node: ast.AST):
        """Called if no explicit visitor function exists for a node."""
        for _field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        self.visit(item)
            elif isinstance(value, ast.AST):
                self.visit(value)

    @override
    def visit_Constant(self, node: ast.Constant):
        name: str
        if node.value in [None, True, False]:
            name = "NameConstant"
        elif isinstance(node.value, (int, float, complex)):
            name = "Num"
        elif isinstance(node.value, str):
            name = "Str"
        elif isinstance(node.value, bytes):
            name = "Bytes"
        elif node.value == Ellipsis:
            name = "Ellipsis"
        else:
            raise RuntimeError(f"Unknown Constant value type {type(node.value)}")

        return self.__visitor(name)(node)
