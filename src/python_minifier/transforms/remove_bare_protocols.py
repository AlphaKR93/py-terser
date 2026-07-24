import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer
from python_minifier._ast.annotation import get_parent

def inherits_protocol(node):
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == 'Protocol':
            return True
        if isinstance(base, ast.Attribute) and base.attr == 'Protocol' and isinstance(base.value, ast.Name) and base.value.id == 'typing':
            return True
    return False

def has_runtime_checkable(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == 'runtime_checkable':
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == 'runtime_checkable' and isinstance(dec.value, ast.Name) and dec.value.id == 'typing':
            return True
    return False

class RemoveBareProtocols(SuiteTransformer):
    def __init__(self):
        super().__init__()
        self.bare_protocols = set()

    def __call__(self, node):
        self.bare_protocols = set()
        referenced_names = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                referenced_names.add(sub.id)

        for sub in ast.walk(node):
            if isinstance(sub, ast.ClassDef) and inherits_protocol(sub) and not has_runtime_checkable(sub):
                parent = get_parent(sub) if hasattr(sub, '_parent') else None
                if isinstance(parent, ast.Module) and not sub.name.startswith('_'):
                    continue
                if sub.name not in referenced_names:
                    self.bare_protocols.add(sub.name)

        return self.visit(node)

    def suite(self, node_list, parent):
        new_list = []
        for node in node_list:
            if isinstance(node, ast.ClassDef) and node.name in self.bare_protocols:
                continue
            visited = self.visit(node)
            if isinstance(visited, list):
                new_list.extend(visited)
            elif visited is not None:
                new_list.append(visited)
        return new_list

    def visit_ClassDef(self, node):
        node.bases = [
            b for b in node.bases
            if not (isinstance(b, ast.Name) and b.id in self.bare_protocols)
        ]
        node.body = self.suite(node.body, parent=node)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        return node
