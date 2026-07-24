from terser.ast import ast, is_constant_node
from ._suite import SuiteTransformer


def find_doc(node):

    if isinstance(node, ast.Attribute) and node.attr == '__doc__':
        raise ValueError('__doc__ found!')

    for child in ast.iter_child_nodes(node):
        find_doc(child)


def _doc_in_module(module):
    try:
        find_doc(module)
        return False
    except Exception:
        return True


def _defines_dunder_doc(module):
    # FLAGS = 0, this runs before resolver.resolve()/bind() - no binding info
    # exists yet, so this has to be a plain structural scan for a module-level
    # `__doc__ = ...` / `__doc__: ... = ...` assignment
    for stmt in module.body:
        if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__doc__' for t in stmt.targets):
            return True

        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == '__doc__':
            return True

    return False


class RemoveLiteralStatements(SuiteTransformer):
    """
    Remove literal expressions from the code

    This includes docstrings
    """
    FLAGS = 0

    @classmethod
    def is_enabled(cls, config, /) -> bool:
        return config.remove_literal_statements

    def __call__(self, node):
        if _doc_in_module(node):
            return node
        return self.visit(node)

    def visit_Module(self, node):
        if _defines_dunder_doc(node):
            node.body = [self.visit(a) for a in node.body]
            return node

        node.body = self.suite(node.body, parent=node)
        return node

    def is_literal_statement(self, node):
        if not isinstance(node, ast.Expr):
            return False

        return is_constant_node(node.value, (ast.Num, ast.Str, ast.NameConstant, ast.Bytes))

    def _is_docstring_position(self, node_list, index, parent):
        # leave docstrings alone here - RemoveDocstrings decides whether to remove them
        if index != 0 or not isinstance(parent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            return False

        node = node_list[0]
        return isinstance(node, ast.Expr) and is_constant_node(node.value, ast.Str)

    def suite(self, node_list, parent):
        without_literals = [
            self.visit(n) for i, n in enumerate(node_list)
            if self._is_docstring_position(node_list, i, parent) or not self.is_literal_statement(n)
        ]

        if len(without_literals) == 0:
            if isinstance(parent, ast.Module):
                return []
            else:
                return [self.add_child(ast.Expr(value=ast.Num(0)), parent=parent)]

        return without_literals
