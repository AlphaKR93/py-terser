import python_minifier._ast as ast
from python_minifier._ast.annotation import get_parent
from python_minifier.transforms.suite_transformer import SuiteTransformer

def get_int_value(value_node):
    if isinstance(value_node, ast.Num):
        return value_node.n
    if isinstance(value_node, ast.Constant) and isinstance(value_node.value, int):
        return value_node.value
    return None

def is_intflag_base(base):
    if isinstance(base, ast.Name) and base.id == 'IntFlag':
        return True
    if isinstance(base, ast.Attribute) and base.attr == 'IntFlag' and isinstance(base.value, ast.Name) and base.value.id == 'enum':
        return True
    return False

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

class InlineIntFlags(SuiteTransformer):
    def __call__(self, node):
        self.flag_maps = {}
        self.classes_to_delete = set()
        self.collect_flags(node)
        return self.visit(node)

    def collect_flags(self, module):
        for node in ast.walk(module):
            if isinstance(node, ast.ClassDef):
                # Check if it inherits from IntFlag
                has_intflag = any(is_intflag_base(b) for b in node.bases)
                other_bases = [b for b in node.bases if not is_intflag_base(b)]

                has_methods = False
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        has_methods = True
                        break

                if has_inline_hint(node):
                    # Validate: other bases or methods is a raise + stop
                    if other_bases or has_methods or not has_intflag:
                        raise RuntimeError(f"inline decorator on IntFlag class '{node.name}' has other bases or methods.")

                if has_intflag:
                    # Check if only IntFlag bases and no methods
                    if not other_bases and not has_methods:
                        # Qualifies for inlining!
                        # Check conditions:
                        parent = get_parent(node)
                        is_nested = isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        is_private = node.name.startswith('__')

                        # In Python, all module-level classes are within module scope.
                        # We inline unconditionally if it qualifies (i.e. is_nested, is_private, or simple module-level).
                        # Let's collect member assignments
                        mapping = {}
                        for sub in node.body:
                            if isinstance(sub, ast.Assign):
                                for target in sub.targets:
                                    if isinstance(target, ast.Name):
                                        val = get_int_value(sub.value)
                                        if val is not None:
                                            mapping[target.id] = val

                        self.flag_maps[node.name] = mapping
                        self.classes_to_delete.add(node.name)

    def visit_Attribute(self, node):
        node = self.generic_visit(node)
        flag_class_name = None
        if isinstance(node.value, ast.Name):
            flag_class_name = node.value.id
        elif isinstance(node.value, ast.Attribute):
            flag_class_name = node.value.attr

        if flag_class_name and flag_class_name in self.flag_maps:
            mapping = self.flag_maps[flag_class_name]
            if node.attr in mapping:
                val = mapping[node.attr]
                # Replace with raw integer constant
                return self.add_child(ast.Constant(value=val), parent=get_parent(node), namespace=node.namespace)
        return node

    def visit_Call(self, node):
        node = self.generic_visit(node)
        flag_class_name = None
        if isinstance(node.func, ast.Name):
            flag_class_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            flag_class_name = node.func.attr

        if flag_class_name and flag_class_name in self.flag_maps:
            if len(node.args) == 1:
                return node.args[0]
            return self.add_child(ast.Constant(value=0), parent=get_parent(node), namespace=node.namespace)
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

        cleaned = []
        for node in visited_list:
            if isinstance(node, ast.ClassDef) and node.name in self.classes_to_delete:
                continue
            cleaned.append(node)
        return cleaned
