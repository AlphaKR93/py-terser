import python_minifier._ast as ast
from python_minifier._ast.annotation import get_parent
from python_minifier.transforms.suite_transformer import SuiteTransformer

def is_call_to(node, names, module=None):
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in names
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if module:
            return func.value.id == module and func.attr in names
        return func.attr in names
    # Handle hints.unreachable or python_minifier.hints.unreachable
    if isinstance(func, ast.Attribute):
        parts = []
        curr = func
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            parts.reverse()
            # check if path matches name
            full_path = ".".join(parts)
            for name in names:
                if full_path.endswith(name):
                    return True
    return False

class Contracts(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_Expr(self, node):
        node.value = self.visit(node.value)
        # If the inner expression was simplified/removed
        if node.value is None:
            return None
        # If it is a call to unreachable, assert_never, assert_type, remove statement
        if is_call_to(node.value, ('unreachable', 'assert_never', 'assert_type')):
            return None
        return node

    def visit_Call(self, node):
        node = self.generic_visit(node)
        # cast(Type, value) -> value
        if is_call_to(node, ('cast',), 'typing'):
            if len(node.args) == 2:
                return node.args[1]
        # If it's a bare cast
        if isinstance(node.func, ast.Name) and node.func.id == 'cast':
            if len(node.args) == 2:
                return node.args[1]

        # Non-statement call to unreachable/assert_never/assert_type -> None
        if is_call_to(node, ('unreachable', 'assert_never', 'assert_type')):
            return self.add_child(ast.Constant(value=None), parent=get_parent(node), namespace=node.namespace)

        return node
