import copy
import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer
from python_minifier.transforms.constant_folding import unparse_expression

def is_literal(node):
    if isinstance(node, (ast.Constant, ast.Num, ast.Str, ast.Bytes, ast.NameConstant)):
        val = getattr(node, 'value', getattr(node, 'n', getattr(node, 's', None)))
        # Check if type is one of the target literal types
        return isinstance(val, (int, float, str, bytes, bool, type(None))) or val is Ellipsis
    return False

class HoistLiterals(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        node.body = self.process_scope_body(node.body, node)
        return node

    def visit_AsyncFunctionDef(self, node):
        node = self.generic_visit(node)
        node.body = self.process_scope_body(node.body, node)
        return node

    def visit_Module(self, node):
        node = self.generic_visit(node)
        node.body = self.process_scope_body(node.body, node)
        return node

    def process_scope_body(self, body, scope_node):
        if isinstance(scope_node, ast.Module):
            return body

        from python_minifier.rename.resolve_names import get_binding
        ref_counts = {}
        for stmt in body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                    ref_counts.setdefault(sub.id, []).append(sub)

        candidates = {}
        for stmt in body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                target_name = stmt.targets[0].id
                if is_literal(stmt.value):
                    try:
                        binding = get_binding(target_name, stmt.targets[0].namespace)
                        is_safe = True
                        store_count = 0
                        for ref in binding.references:
                            # If the reference is not in the same namespace, or if it is nonlocal, do not inline
                            if getattr(ref, 'namespace', None) is not stmt.targets[0].namespace:
                                is_safe = False
                                break
                            if isinstance(ref, ast.Name) and isinstance(ref.ctx, ast.Store):
                                store_count += 1
                        if store_count > 1:
                            is_safe = False
                        if is_safe:
                            candidates[target_name] = (stmt, stmt.value)
                    except Exception:
                        pass

        inlined_names = {}
        for var_name, (assign_node, literal_node) in candidates.items():
            refs = ref_counts.get(var_name, [])
            if 1 <= len(refs) <= 2:
                try:
                    literal_str = unparse_expression(literal_node)
                except Exception:
                    continue

                original_cost = len(var_name) + len(literal_str) + 4 + len(refs) * len(var_name)
                inlined_cost = len(refs) * len(literal_str)

                if inlined_cost < original_cost:
                    inlined_names[var_name] = (assign_node, literal_node)

        if inlined_names:
            class Inliner(ast.NodeTransformer):
                def __init__(self, inlined, add_child, parent):
                    self.inlined = inlined
                    self.add_child = add_child
                    self.parent = parent
                def visit_Name(self, n):
                    if n.id in self.inlined and isinstance(n.ctx, ast.Load):
                        _, lit = self.inlined[n.id]
                        new_lit = copy.deepcopy(lit)
                        return self.add_child(new_lit, parent=self.parent)
                    return n

            new_body = []
            for stmt in body:
                is_inlined_assign = False
                for name, (assign_node, _) in inlined_names.items():
                    if stmt is assign_node:
                        is_inlined_assign = True
                        break
                if is_inlined_assign:
                    continue

                new_stmt = Inliner(inlined_names, self.add_child, scope_node).visit(stmt)
                new_body.append(new_stmt)
            return new_body

        return body
