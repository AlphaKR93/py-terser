import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

def is_typing_decorator(dec):
    if isinstance(dec, ast.Call):
        dec = dec.func

    if isinstance(dec, ast.Name) and dec.id in ('override', 'final'):
        return True
    if isinstance(dec, ast.Attribute) and dec.attr in ('override', 'final') and isinstance(dec.value, ast.Name) and dec.value.id == 'typing':
        return True

    if isinstance(dec, ast.Attribute):
        parts = []
        curr = dec
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            parts.reverse()
            full_path = ".".join(parts)
            if full_path.startswith("python_minifier.hints") or full_path.startswith("hints"):
                return True
    return False

class RemoveTypingDecorators(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_ClassDef(self, node):
        node.decorator_list = [self.visit(d) for d in node.decorator_list if not is_typing_decorator(d)]
        node.bases = [self.visit(b) for b in node.bases]
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]
        node.body = self.suite(node.body, parent=node)
        return node

    def visit_FunctionDef(self, node):
        node.decorator_list = [self.visit(d) for d in node.decorator_list if not is_typing_decorator(d)]
        node.args = self.visit(node.args)
        if hasattr(node, 'returns') and node.returns is not None:
            node.returns = self.visit(node.returns)
        node.body = self.suite(node.body, parent=node)
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)
