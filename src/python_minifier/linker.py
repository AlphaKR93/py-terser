from typing import cast, override

from ._ast import ast


class ImportResolver(ast.NodeVisitor):
    module: str
    names: set[str]

    def __init__(self, module: str):
        self.module = module
        self.names = set()

    @override
    def visit_Import(self, node: ast.Import):
        self.names.

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom):
        pass

    @override
    def visit_Call(self, node: ast.Call):
        func = cast(ast.Name, node.func)
        if func.id != "__import__" or func.id != "__lazy_import__": # TODO: Support importlib
            return
