import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

def get_all_names(module):
    names = set()
    for stmt in module.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name) and target.id == '__all__':
                if isinstance(stmt.value, (ast.List, ast.Tuple)):
                    for elt in stmt.value.elts:
                        val = getattr(elt, 'value', getattr(elt, 's', None))
                        if isinstance(val, str):
                            names.add(val)
    return names

def is_referenced_in_scope(scope, bound_name):
    # Walk scope to find Name loads/stores
    for sub in ast.walk(scope):
        if isinstance(sub, ast.Name) and sub.id == bound_name:
            return True
    return False

def is_declared_nonlocal_or_global(scope, bound_name):
    if not scope:
        return False
    for sub in ast.walk(scope):
        if isinstance(sub, ast.Nonlocal) and bound_name in sub.names:
            return True
        if isinstance(sub, ast.Global) and bound_name in sub.names:
            return True
    return False

class UnusedImportRemover(ast.NodeTransformer):
    def __init__(self, all_names, module_node):
        self.all_names = all_names
        self.module = module_node
        self.current_scope = None

    def visit_Module(self, node):
        self.current_scope = node
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        old_scope = self.current_scope
        self.current_scope = node
        node = self.generic_visit(node)
        self.current_scope = old_scope
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_Import(self, node):
        new_names = []
        for alias in node.names:
            bound_name = alias.asname if alias.asname else alias.name
            if '.' in bound_name:
                bound_name = bound_name.split('.')[0]

            referenced = False
            if bound_name in self.all_names and isinstance(self.current_scope, ast.Module):
                referenced = True
            elif is_declared_nonlocal_or_global(self.current_scope, bound_name):
                referenced = is_referenced_in_scope(self.module, bound_name)
            else:
                referenced = is_referenced_in_scope(self.current_scope, bound_name)

            if referenced:
                new_names.append(alias)

        if not new_names:
            return None
        node.names = new_names
        return node

    def visit_ImportFrom(self, node):
        if node.module == '__future__':
            return node
        if len(node.names) == 1 and node.names[0].name == '*':
            return node

        new_names = []
        for alias in node.names:
            bound_name = alias.asname if alias.asname else alias.name

            referenced = False
            if bound_name in self.all_names and isinstance(self.current_scope, ast.Module):
                referenced = True
            elif is_declared_nonlocal_or_global(self.current_scope, bound_name):
                referenced = is_referenced_in_scope(self.module, bound_name)
            else:
                referenced = is_referenced_in_scope(self.current_scope, bound_name)

            if referenced:
                new_names.append(alias)

        if not new_names:
            return None
        node.names = new_names
        return node

class CleanupImports(SuiteTransformer):
    def __init__(self, config=None):
        super().__init__()
        self.config = config

    def __call__(self, node):
        # 1. Combine adjacent imports first
        self.module = node
        node = self.visit(node)

        # 2. Remove unused imports
        if not getattr(node, 'is_init', False):
            all_names = get_all_names(node)
            if self.config and self.config.module_name_map:
                mapped_names = set()
                for name in all_names:
                    mapped_name = self.config.module_name_map.get(name, name)
                    mapped_names.add(mapped_name)
                all_names = mapped_names
            remover = UnusedImportRemover(all_names, node)
            node = remover.visit(node)

        return node

    def sort_aliases(self, aliases, module):
        ref_counts = {}
        for child in ast.walk(module):
            if isinstance(child, ast.Name):
                ref_counts[child.id] = ref_counts.get(child.id, 0) + 1

        def get_count(alias):
            name = alias.asname if alias.asname else alias.name
            if '.' in name:
                name = name.split('.')[0]
            return ref_counts.get(name, 0)

        return sorted(aliases, key=lambda a: (-get_count(a), a.name))

    def _combine_import(self, node_list, parent):
        alias = []
        namespace = None

        for statement in node_list:
            if isinstance(statement, ast.Import):
                namespace = statement.namespace
                alias += statement.names
            else:
                if alias:
                    sorted_alias = self.sort_aliases(alias, self.module)
                    yield self.add_child(ast.Import(names=sorted_alias), parent=parent, namespace=namespace)
                    alias = []
                yield statement

        if alias:
            sorted_alias = self.sort_aliases(alias, self.module)
            yield self.add_child(ast.Import(names=sorted_alias), parent=parent, namespace=namespace)

    def _combine_import_from(self, node_list, parent):
        prev_import = None
        alias = []

        def combine(statement):
            if not isinstance(statement, ast.ImportFrom):
                return False
            if len(statement.names) == 1 and statement.names[0].name == '*':
                return False
            if prev_import is None:
                return True
            if statement.module == prev_import.module and statement.level == prev_import.level:
                return True
            return False

        for statement in node_list:
            if combine(statement):
                prev_import = statement
                alias += statement.names
            else:
                if alias:
                    sorted_alias = self.sort_aliases(alias, self.module)
                    yield self.add_child(
                        ast.ImportFrom(module=prev_import.module, names=sorted_alias, level=prev_import.level),
                        parent=parent,
                        namespace=prev_import.namespace
                    )
                    alias = []
                yield statement

        if alias:
            sorted_alias = self.sort_aliases(alias, self.module)
            yield self.add_child(
                ast.ImportFrom(module=prev_import.module, names=sorted_alias, level=prev_import.level),
                parent=parent,
                namespace=prev_import.namespace
            )

    def suite(self, node_list, parent):
        a = list(self._combine_import(node_list, parent))
        b = list(self._combine_import_from(a, parent))
        return self.clean_suite([self.visit(n) for n in b if n is not None], parent)
