import terser.ast_compat as ast
from terser.ast_annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer
from terser.transforms.constant_folding import unparse_expression

def get_parent_safe(node):
    if hasattr(node, 'parent') and node.parent is not None:
        return node.parent
    return None

def clean_copy_node(node):
    try:
        expr_str = unparse_expression(node)
        return ast.parse(expr_str, mode='eval').body
    except Exception:
        import copy
        # Fallback if unparsing fails (e.g. for non-expression nodes if any)
        # But we strip parent pointers before copying to avoid copying the whole AST
        old_parent = getattr(node, 'parent', None)
        if hasattr(node, 'parent'):
            delattr(node, 'parent')
        copied = copy.deepcopy(node)
        if old_parent is not None:
            node.parent = old_parent
        return copied

class SubstitutionVisitor(ast.NodeTransformer):
    def __init__(self, param_map):
        self.param_map = param_map

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.param_map:
            return clean_copy_node(self.param_map[node.id])
        return node

def is_inline_decorator(dec):
    if isinstance(dec, ast.Name) and dec.id == 'inline':
        return True
    if isinstance(dec, ast.Attribute) and dec.attr == 'inline' and isinstance(dec.value, ast.Name) and dec.value.id == 'terser':
        return True
    if isinstance(dec, ast.Attribute) and dec.attr == 'inline':
        val = dec.value
        if isinstance(val, ast.Attribute) and val.attr == 'hints' and isinstance(val.value, ast.Name) and val.value.id == 'terser':
            return True
    return False

class InlineFunctions(SuiteTransformer):
    """
    Inline local functions called exactly once.
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_FunctionDef(self, node):
        self.inlined_funcs = set()
        node.body = self.suite(node.body, parent=node)
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            parent_func = self.find_parent_function(node)
            if parent_func:
                local_def = self.find_local_def(parent_func, func_name)
                if local_def and self.is_inlinable(parent_func, local_def, node):
                    param_names = [a.arg for a in local_def.args.args]
                    param_map = dict(zip(param_names, node.args))
                    ret_val = local_def.body[0].value
                    if ret_val is None:
                        replacement = self.add_child(ast.NameConstant(value=None), parent=get_parent(node), namespace=node.namespace)
                    else:
                        subst = SubstitutionVisitor(param_map)
                        subst_val = subst.visit(clean_copy_node(ret_val))
                        replacement = self.add_child(subst_val, parent=get_parent(node), namespace=node.namespace)
                    self.inlined_funcs.add(func_name)
                    return replacement
        return node

    def find_parent_function(self, node):
        curr = get_parent_safe(node)
        while curr:
            if isinstance(curr, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return curr
            curr = get_parent_safe(curr)
        return None

    def find_local_def(self, parent_func, name):
        for statement in parent_func.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name == name:
                return statement
        return None

    def is_inlinable(self, parent_func, local_def, call_node):
        if len(local_def.body) != 1 or not isinstance(local_def.body[0], ast.Return):
            return False

        args_spec = local_def.args
        if args_spec.vararg or args_spec.kwarg or args_spec.kwonlyargs or args_spec.defaults:
            return False

        if len(args_spec.args) != len(call_node.args):
            return False

        refs = []
        for n in ast.walk(parent_func):
            if isinstance(n, ast.Name) and n.id == local_def.name:
                refs.append(n)
        
        has_inline_hint = False
        if local_def.decorator_list:
            for dec in local_def.decorator_list:
                if is_inline_decorator(dec):
                    has_inline_hint = True
                    break

        if len(refs) == 2 or has_inline_hint:
            return True

        return False

    def suite(self, node_list, parent):
        visited_list = []
        for node in node_list:
            visited = self.visit(node)
            if visited is not None:
                if isinstance(visited, list):
                    visited_list.extend(visited)
                else:
                    visited_list.append(visited)
        
        cleaned = []
        for node in visited_list:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in self.inlined_funcs:
                continue
            cleaned.append(node)
        return cleaned
