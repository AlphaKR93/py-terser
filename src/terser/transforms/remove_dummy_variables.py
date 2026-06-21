import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer
from terser.rename.resolve_names import get_binding

def is_all_underscore(name):
    return name and all(c == '_' for c in name)

def check_all_underscore_refs(module):
    pass

def has_all_underscore_load_refs(name, scope):
    if not scope:
        return True
    for node in ast.walk(scope):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
            parent = get_parent(node)
            is_allowed = False
            while parent:
                if isinstance(parent, ast.Lambda):
                    is_allowed = True
                    break
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if len(parent.body) == 1:
                        is_allowed = True
                    break
                parent = get_parent(parent)
            if not is_allowed:
                return True
    return False

def is_literal(node):
    if isinstance(node, (ast.Constant, ast.Num, ast.Str, ast.Bytes, ast.NameConstant)):
        return True
    if isinstance(node, ast.Tuple) or isinstance(node, ast.List):
        return all(is_literal(elt) for elt in node.elts)
    return False

def has_load_reference(binding):
    if not binding:
        return True
    for ref in binding.references:
        if isinstance(ref, ast.Name) and isinstance(ref.ctx, ast.Load):
            return True
    return False

class RemoveDummyVariables(SuiteTransformer):
    def __call__(self, node):
        check_all_underscore_refs(node)
        return self.visit(node)

    def visit_Assign(self, node):
        node.value = self.visit(node.value)
        # Handle single target ast.Name assignment
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            if is_all_underscore(target_name):
                namespace = getattr(node.targets[0], 'namespace', None)
                if namespace and has_all_underscore_load_refs(target_name, namespace):
                    return node
                if is_literal(node.value):
                    return None
                return self.add_child(ast.Expr(value=node.value), parent=get_parent(node))
            
            # Retrieve binding to check if it has load references
            try:
                namespace = node.targets[0].namespace
                if not isinstance(namespace, (ast.Module, ast.ClassDef)):
                    binding = get_binding(target_name, namespace)
                    if not has_load_reference(binding):
                        if is_literal(node.value):
                            return None
                        return self.add_child(ast.Expr(value=node.value), parent=get_parent(node))
            except Exception:
                pass
        return node

    def visit_AnnAssign(self, node):
        if node.value:
            node.value = self.visit(node.value)
        if isinstance(node.target, ast.Name):
            target_name = node.target.id
            if is_all_underscore(target_name):
                namespace = getattr(node.target, 'namespace', None)
                if namespace and has_all_underscore_load_refs(target_name, namespace):
                    return node
                if not node.value or is_literal(node.value):
                    return None
                return self.add_child(ast.Expr(value=node.value), parent=get_parent(node))
            try:
                namespace = node.target.namespace
                if not isinstance(namespace, (ast.Module, ast.ClassDef)):
                    binding = get_binding(target_name, namespace)
                    if not has_load_reference(binding):
                        if not node.value or is_literal(node.value):
                            return None
                        return self.add_child(ast.Expr(value=node.value), parent=get_parent(node))
            except Exception:
                pass
        return node

    def visit_ExceptHandler(self, node):
        node.body = self.suite(node.body, parent=node)
        if node.name:
            # Check if referenced in body
            has_read = False
            for child in node.body:
                for sub in ast.walk(child):
                    if isinstance(sub, ast.Name) and sub.id == node.name and isinstance(sub.ctx, ast.Load):
                        has_read = True
                        break
                if has_read:
                    break
            if not has_read:
                node.name = None
        return node

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        # Collect all Name nodes in the function body
        referenced_names = set()
        for child in node.body:
            for sub in ast.walk(child):
                if isinstance(sub, ast.Name):
                    referenced_names.add(sub.id)
        
        # Clean Nonlocal/Global statements
        cleaned_body = []
        for stmt in node.body:
            if isinstance(stmt, ast.Nonlocal):
                stmt.names = [name for name in stmt.names if name in referenced_names]
                if stmt.names:
                    cleaned_body.append(stmt)
            elif isinstance(stmt, ast.Global):
                stmt.names = [name for name in stmt.names if name in referenced_names]
                if stmt.names:
                    cleaned_body.append(stmt)
            else:
                cleaned_body.append(stmt)
        node.body = cleaned_body
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)
