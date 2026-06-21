import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer

def is_overload(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == 'overload':
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == 'overload' and isinstance(dec.value, ast.Name) and dec.value.id == 'typing':
            return True
    return False

def is_terser_hint(node):
    if isinstance(node, ast.Attribute):
        if node.attr == 'hints' and isinstance(node.value, ast.Name) and node.value.id == 'terser':
            return True
        return is_terser_hint(node.value)
    return False

def clean_decorators(decorators):
    cleaned = []
    for dec in decorators:
        # @typing.override / @typing.final
        if isinstance(dec, ast.Name) and dec.id in ('override', 'final'):
            continue
        if isinstance(dec, ast.Attribute):
            if dec.attr in ('override', 'final') and isinstance(dec.value, ast.Name) and dec.value.id == 'typing':
                continue
            if is_terser_hint(dec):
                continue
        # @contract(...)
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == 'contract':
            continue
        if isinstance(dec, ast.Name) and dec.id == 'contract':
            continue
        # @lambda _: _()
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Lambda):
            continue
        cleaned.append(dec)
    return cleaned

class DecoratorsAndContractsSweeper(SuiteTransformer):
    """
    Remove overload functions, contract/hint decorators, type overrides/finals, and cast/never calls.
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_ClassDef(self, node):
        node.decorator_list = clean_decorators([self.visit(d) for d in node.decorator_list])
        node.bases = [self.visit(b) for b in node.bases]
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]
        node.body = self.suite(node.body, parent=node)
        return node

    def visit_FunctionDef(self, node):
        node.decorator_list = clean_decorators([self.visit(d) for d in node.decorator_list])
        node.args = self.visit(node.args)
        if hasattr(node, 'returns') and node.returns is not None:
            node.returns = self.visit(node.returns)
        node.body = self.suite(node.body, parent=node)
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        # typing.cast(Type, value) -> value
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'cast' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'typing':
            if len(node.args) == 2:
                return node.args[1]
        if isinstance(node.func, ast.Name) and node.func.id == 'cast':
            if len(node.args) == 2:
                return node.args[1]

        # unreachable() / assert_never() -> None
        if isinstance(node.func, ast.Name) and node.func.id in ('unreachable', 'assert_never'):
            return self.add_child(ast.NameConstant(value=None), parent=get_parent(node), namespace=node.namespace)
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'assert_never' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'typing':
            return self.add_child(ast.NameConstant(value=None), parent=get_parent(node), namespace=node.namespace)
        return node

    def suite(self, node_list, parent):
        cleaned = []
        for node in node_list:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_overload(node):
                continue
            visited = self.visit(node)
            if visited is None:
                continue
            if isinstance(visited, ast.Expr) and isinstance(visited.value, (ast.NameConstant, ast.Constant)):
                if visited.value.value is None:
                    continue
            if isinstance(visited, list):
                cleaned.extend(visited)
            else:
                cleaned.append(visited)
        return cleaned
