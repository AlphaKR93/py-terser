from python_minifier._ast.tree._module import Namespace
from typing import override
from .._ast import ast


def not_none[T](value: T | None) -> T:
    if value is None:
        raise TypeError
    return value


class ModuleImportResolver(ast.NodeVisitor):
    __names: set[str]
    __ns: Namespace

    def __init__(self, namespace: Namespace):
        self.__names = set()
        self.__ns = namespace

    def __call__(self, node: ast.AST):
        self.visit(node)
        return self.__names

    @override
    def visit_Import(self, node: ast.Import):
        self.__names |= {name.name for name in node.names}

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.level == 0:
            self.__names |= {str(node.module) + name.name for name in node.names}
            return

        i = node.level
        ns = self.__ns
        while i := i - 1: ns = not_none(ns.parent)

        ns_ = str(ns)
        self.__names = {ns_ + name.name for name in node.names}

    @override
    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name) or (node.func.id != "__import__" and node.func.id != "__lazy_import__"):
            return

        target = node.args[0]
        if not isinstance(target, ast.Constant):
            return
        elif not isinstance(target.value, str):
            return

        self.__names.add(target.value)
