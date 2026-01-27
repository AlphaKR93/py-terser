from typing import TypeVar, override

import python_minifier.ast as ast

class NodeVisitor(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> ast.AST | None: ...

_T = TypeVar("_T", bound=ast.AST)

class SuiteTransformer(NodeVisitor):
    def __call__(self, node: _T) -> _T: ...
    @override
    def visit(self, node: _T) -> _T: ...
    @override
    def generic_visit(self, node: ast.AST) -> ast.AST: ...
