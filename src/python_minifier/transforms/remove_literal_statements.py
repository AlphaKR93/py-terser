import python_minifier.ast as ast

from python_minifier.transforms.suite_transformer import SuiteTransformer
from python_minifier.util import is_constant_node


def find_doc(node):
    if isinstance(node, ast.Attribute) and node.attr == "__doc__":
        raise ValueError("__doc__ found!")

    for child in ast.iter_child_nodes(node):
        find_doc(child)


def _doc_in_module(module):
    try:
        find_doc(module)
        return False
    except Exception:
        return True


class RemoveLiteralStatements(SuiteTransformer):
    """
    Remove literal expressions and other side-effect free statements from the code
    """

    def __call__(self, node):
        if _doc_in_module(node):
            return node
        return self.visit(node)

    def visit_Module(self, node):
        for binding in node.bindings:
            if binding.name == "__doc__":
                node.body = [self.visit(a) for a in node.body]
                return node

        node.body = self.suite(node.body, parent=node)
        return node

    def is_removable_expression(self, node):
        """
        Check if an expression is side-effect free and safe to remove.
        Includes literals, names, attributes, subscripts, and containers of these.
        """

        # Base case: Constants (literals)
        if isinstance(node, ast.Constant):
            return True

        # Python < 3.8 constants compatibility
        if hasattr(ast, "Num") and isinstance(node, (ast.Num, ast.Str, ast.Bytes, ast.NameConstant, ast.Ellipsis)):
            return True

        # Variable access (reading a variable is generally considered side-effect free for removal purposes)
        if isinstance(node, ast.Name):
            return isinstance(node.ctx, ast.Load)

        # Attribute access (e.g. obj.attr)
        # While __getattribute__ could have side effects, code used as 'comments' or type hints
        # typically does not rely on them.
        if isinstance(node, ast.Attribute):
            return self.is_removable_expression(node.value) and isinstance(node.ctx, ast.Load)

        # Subscript access (e.g. obj[key], List[int])
        # While __getitem__/class_getitem could have side effects, type hints are safe to remove.
        if isinstance(node, ast.Subscript):
            if not self.is_removable_expression(node.value):
                return False
            if not isinstance(node.ctx, ast.Load):
                return False

            # Check slice
            # Python < 3.9 uses Index/Slice/ExtSlice, Python 3.9+ uses direct nodes
            slice_node = node.slice
            if hasattr(ast, "Index") and isinstance(slice_node, ast.Index):
                return self.is_removable_expression(slice_node.value)
            elif hasattr(ast, "Slice") and isinstance(slice_node, ast.Slice):
                return (
                    (not slice_node.lower or self.is_removable_expression(slice_node.lower))
                    and (not slice_node.upper or self.is_removable_expression(slice_node.upper))
                    and (not slice_node.step or self.is_removable_expression(slice_node.step))
                )
            elif hasattr(ast, "ExtSlice") and isinstance(slice_node, ast.ExtSlice):
                return all(self.is_removable_expression(dim) for dim in slice_node.dims)
            else:
                # Python 3.9+ or other simple slice nodes
                return self.is_removable_expression(slice_node)

        # Binary Operations (e.g. 1 + 2, int | str)
        if isinstance(node, ast.BinOp):
            return self.is_removable_expression(node.left) and self.is_removable_expression(node.right)

        # Unary Operations (e.g. -1, ~0)
        if isinstance(node, ast.UnaryOp):
            return self.is_removable_expression(node.operand)

        # Boolean Operations (e.g. True and False)
        if isinstance(node, ast.BoolOp):
            return all(self.is_removable_expression(val) for val in node.values)

        # Containers (List, Tuple, Set)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return all(self.is_removable_expression(elt) for elt in node.elts) and isinstance(node.ctx, ast.Load)

        # Dictionary
        if isinstance(node, ast.Dict):
            return all(
                (k is None or self.is_removable_expression(k)) and self.is_removable_expression(v)
                for k, v in zip(node.keys, node.values)
            )

        return False

    def is_literal_statement(self, node):
        if not isinstance(node, ast.Expr):
            return False

        # Check if the expression value is removable
        return self.is_removable_expression(node.value)

    def suite(self, node_list, parent):
        without_literals = [self.visit(n) for n in node_list if not self.is_literal_statement(n)]

        if len(without_literals) == 0:
            if isinstance(parent, ast.Module):
                return []
            else:
                return [self.add_child(ast.Expr(value=ast.Num(0)), parent=parent)]

        return without_literals
