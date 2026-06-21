import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer

def get_int_value(value_node):
    if isinstance(value_node, ast.Num):
        return value_node.n
    if isinstance(value_node, ast.Constant) and isinstance(value_node.value, int):
        return value_node.value
    return None

class IntFlagSimplifier(SuiteTransformer):
    """
    Simplify methodless IntFlag classes by replacing flag refs with raw integers and deleting the classes.
    """
    def __call__(self, node):
        self.flag_maps = {}
        self.classes_to_delete = set()
        self.collect_flags(node)
        return self.visit(node)

    def collect_flags(self, module):
        for node in ast.walk(module):
            if isinstance(node, ast.ClassDef):
                is_intflag = False
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == 'IntFlag':
                        is_intflag = True
                    elif isinstance(base, ast.Attribute) and base.attr == 'IntFlag' and isinstance(base.value, ast.Name) and base.value.id == 'enum':
                        is_intflag = True
                
                if is_intflag:
                    has_methods = False
                    mapping = {}
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            has_methods = True
                            break
                        if isinstance(sub, ast.Assign):
                            for target in sub.targets:
                                if isinstance(target, ast.Name):
                                    val = get_int_value(sub.value)
                                    if val is not None:
                                        mapping[target.id] = val
                    if not has_methods:
                        self.flag_maps[node.name] = mapping
                        self.classes_to_delete.add(node.name)

    def visit_Attribute(self, node):
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id in self.flag_maps:
            mapping = self.flag_maps[node.value.id]
            if node.attr in mapping:
                val = mapping[node.attr]
                return self.add_child(ast.Num(n=val), parent=get_parent(node), namespace=node.namespace)
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
