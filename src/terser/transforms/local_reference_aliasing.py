import terser.ast_compat as ast
from terser.ast_annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer

# List of built-in names or keywords that cannot be assigned to
UNASSIGNABLE = {'None', 'True', 'False', 'self', 'cls'}

class LocalReferenceAliaser(SuiteTransformer):
    """
    Alias frequently referenced reserved/global names to short locals.
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_FunctionDef(self, node):
        # Scan body for references to non-local, non-keyword, non-class names
        # We only look at names loaded (Load ctx)
        reads = {}
        # Also collect all names bound locally to avoid clashing or aliasing local variables
        local_bounds = set()

        class Scanner(ast.NodeVisitor):
            def visit_Name(self, n):
                if isinstance(n.ctx, ast.Load):
                    if n.id not in UNASSIGNABLE:
                        reads[n.id] = reads.get(n.id, 0) + 1
                elif isinstance(n.ctx, ast.Store):
                    local_bounds.add(n.id)
            
            def visit_FunctionDef(self, n):
                # count function name as write, but don't scan inner function body
                local_bounds.add(n.name)

            def visit_AsyncFunctionDef(self, n):
                local_bounds.add(n.name)

            def visit_ClassDef(self, n):
                local_bounds.add(n.name)

        scanner = Scanner()
        for child in node.body:
            scanner.visit(child)
        
        # Find which names qualify for aliasing
        self.alias_map = {} # name -> alias_name
        self.inserted_assigns = []

        for name, ref_count in reads.items():
            if name in local_bounds:
                continue
            
            L = len(name)
            # We want: ref_count * (L - 1) - (L + 5) > 0
            if ref_count * (L - 1) - (L + 5) > 0:
                alias_name = '_ref_' + name
                self.alias_map[name] = alias_name
                
                # Create assignment node: alias_name = name
                target = self.add_child(ast.Name(id=alias_name, ctx=ast.Store()), parent=node, namespace=node.namespace)
                value = self.add_child(ast.Name(id=name, ctx=ast.Load()), parent=node, namespace=node.namespace)
                assign = self.add_child(ast.Assign(targets=[target], value=value), parent=node, namespace=node.namespace)
                self.inserted_assigns.append(assign)
        
        # If we have any aliases, visit the body to replace loads, and prepend assignments
        if self.alias_map:
            node.body = self.suite(node.body, parent=node)
            node.body = self.inserted_assigns + node.body
        else:
            node.body = self.suite(node.body, parent=node)
        
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and hasattr(self, 'alias_map') and node.id in self.alias_map:
            return self.add_child(ast.Name(id=self.alias_map[node.id], ctx=ast.Load()), parent=get_parent(node), namespace=node.namespace)
        return node
