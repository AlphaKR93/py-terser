import copy
import python_minifier._ast as ast
from python_minifier._ast.annotation import get_parent
from python_minifier.transforms.suite_transformer import SuiteTransformer
from python_minifier.transforms.constant_folding import unparse_expression

def get_parent_safe(node):
    try:
        return get_parent(node)
    except ValueError:
        return None

def clean_copy_node(node):
    try:
        expr_str = unparse_expression(node)
        return ast.parse(expr_str, mode='eval').body
    except Exception:
        # Fallback using copy.deepcopy
        old_parent = getattr(node, 'parent', None)
        if hasattr(node, 'parent'):
            delattr(node, 'parent')
        copied = copy.deepcopy(node)
        if old_parent is not None:
            node.parent = old_parent
        return copied

class SubstitutionVisitor(ast.NodeTransformer):
    def __init__(self, param_map, parent_node, add_child):
        self.param_map = param_map
        self.parent_node = parent_node
        self.add_child = add_child

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.param_map:
            copied = clean_copy_node(self.param_map[node.id])
            return self.add_child(copied, parent=self.parent_node)
        return node

def is_inline_decorator(dec):
    if isinstance(dec, ast.Name) and dec.id == 'inline':
        return True
    if isinstance(dec, ast.Attribute) and dec.attr == 'inline' and isinstance(dec.value, ast.Name) and dec.value.id == 'python_minifier':
        return True
    if isinstance(dec, ast.Attribute) and dec.attr == 'inline':
        val = dec.value
        if isinstance(val, ast.Attribute) and val.attr == 'hints' and isinstance(val.value, ast.Name) and val.value.id == 'python_minifier':
            return True
    return False

def has_inline_hint(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    return any(is_inline_decorator(d) for d in node.decorator_list)

class InlineFunctions(SuiteTransformer):
    def __init__(self):
        super().__init__()
        self.inlined_funcs = set() # set of function name strings
        self.actually_inlined_funcs = set()

    def __call__(self, node):
        self.inlined_funcs = set()
        self.actually_inlined_funcs = set()
        # Find all function definitions and count references in the whole module
        all_defs = {} # name -> node
        all_refs = {} # name -> list of Name nodes
        all_store_refs = {} # name -> list of Name nodes
        nonlocal_names = set()
        global_names = set()

        for sub in ast.walk(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_defs[sub.name] = sub
            elif isinstance(sub, ast.Name):
                if isinstance(sub.ctx, ast.Load):
                    all_refs.setdefault(sub.id, []).append(sub)
                elif isinstance(sub.ctx, ast.Store):
                    all_store_refs.setdefault(sub.id, []).append(sub)
            elif isinstance(sub, ast.Nonlocal):
                nonlocal_names.update(sub.names)
            elif isinstance(sub, ast.Global):
                global_names.update(sub.names)

        # Determine which are inlinable
        for name, func_def in all_defs.items():
            # Body must be single Return statement
            if len(func_def.body) != 1 or not isinstance(func_def.body[0], ast.Return):
                continue

            # Args must not have vararg, kwarg, kwonlyargs, defaults
            args_spec = func_def.args
            if args_spec.vararg or args_spec.kwarg or args_spec.kwonlyargs or args_spec.defaults:
                continue

            # If name is assigned to somewhere, or declared nonlocal/global, do not inline
            if name in all_store_refs or name in nonlocal_names or name in global_names:
                continue

            # Reference count check
            refs = all_refs.get(name, [])
            inline_it = False

            parent_node = get_parent_safe(func_def)
            is_module_level = isinstance(parent_node, ast.Module)

            if has_inline_hint(func_def):
                inline_it = True
            elif is_module_level:
                # Module-level functions only inlined if private (name starts with _ or __) and used exactly once
                if (name.startswith('_') or name.startswith('__')) and len(refs) == 1:
                    inline_it = True
            else:
                # Nested functions unconditionally inlinable when called once
                if len(refs) == 1:
                    inline_it = True

            if inline_it:
                self.inlined_funcs.add(name)

        # Process the AST to perform inline replacement
        return self.visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in self.inlined_funcs:
            # We must find the def to get its parameters and body
            # Walk the tree from the top to find the definition of this function
            # Since names are unique or resolved, we can just find it
            func_def = None
            # Find in the parent hierarchy or walk the top node
            # Let's search from module level (get_parent until module)
            curr = node
            while True:
                p = get_parent_safe(curr)
                if p is None:
                    break
                curr = p

            for sub in ast.walk(curr):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == node.func.id:
                    func_def = sub
                    break

            if func_def:
                param_names = [a.arg for a in func_def.args.args]
                if len(param_names) == len(node.args):
                    param_map = dict(zip(param_names, node.args))
                    ret_val = func_def.body[0].value

                    if ret_val is None:
                        self.actually_inlined_funcs.add(node.func.id)
                        return self.add_child(ast.Constant(value=None), parent=get_parent(node), namespace=node.namespace)
                    else:
                        subst = SubstitutionVisitor(param_map, get_parent(node), self.add_child)
                        subst_val = subst.visit(clean_copy_node(ret_val))
                        self.actually_inlined_funcs.add(node.func.id)
                        return self.add_child(subst_val, parent=get_parent(node), namespace=node.namespace)

        return node

    def suite(self, node_list, parent):
        visited_list = []
        for node in node_list:
            visited = self.visit(node)
            if visited is not None:
                if isinstance(visited, list):
                    visited_list.extend(visited)
                else:
                    visited_list.append(visited)

        # Remove definitions of inlined functions
        cleaned = []
        for node in visited_list:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in self.actually_inlined_funcs:
                continue
            cleaned.append(node)
        return cleaned
