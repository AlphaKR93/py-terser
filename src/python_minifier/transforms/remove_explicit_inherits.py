import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

class RemoveExplicitInherits(SuiteTransformer):
    def __init__(self):
        super().__init__()
        self.folded_abc = False

    def __call__(self, node):
        self.folded_abc = False
        node = self.visit(node)

        if self.folded_abc and isinstance(node, ast.Module):
            # 1. Ensure 'ABC' is imported
            has_abc = False
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.module == 'abc':
                    if any(n.name == 'ABC' for n in stmt.names):
                        has_abc = True
                elif isinstance(stmt, ast.Import):
                    if any(n.name == 'abc' for n in stmt.names):
                        has_abc = True

            if not has_abc:
                new_import = self.add_child(
                    ast.ImportFrom(module='abc', names=[ast.alias(name='ABC', asname=None)], level=0),
                    parent=node
                )
                node.body.insert(0, new_import)

            # 2. Check if ABCMeta is still used. If not, remove from imports.
            abc_meta_count = 0
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id == 'ABCMeta':
                    abc_meta_count += 1

            if abc_meta_count == 0:
                new_body = []
                for stmt in node.body:
                    if isinstance(stmt, ast.ImportFrom) and stmt.module == 'abc':
                        stmt.names = [n for n in stmt.names if n.name != 'ABCMeta']
                        if not stmt.names:
                            continue
                    new_body.append(stmt)
                node.body = new_body

        return node

    def visit_ClassDef(self, node):
        node.bases = [
            b for b in node.bases
            if not (isinstance(b, ast.Name) and b.id == 'object')
        ]

        new_keywords = []
        for kw in node.keywords:
            if kw.arg == 'metaclass' and isinstance(kw.value, ast.Name) and kw.value.id == 'ABCMeta':
                if not any(isinstance(b, ast.Name) and b.id == 'ABC' for b in node.bases):
                    node.bases.append(self.add_child(ast.Name(id='ABC', ctx=ast.Load()), parent=node))
                self.folded_abc = True
            else:
                new_keywords.append(kw)
        node.keywords = new_keywords

        node.body = self.suite(node.body, parent=node)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        return node
