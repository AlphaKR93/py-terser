import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

class CombineImports(SuiteTransformer):
    """
    Combine multiple import statements where possible and sort them by reference frequency.
    """
    def __call__(self, node):
        self.module = node
        return self.visit(node)

    def sort_aliases(self, aliases, module):
        ref_counts = {}
        for child in ast.walk(module):
            if isinstance(child, ast.Name):
                ref_counts[child.id] = ref_counts.get(child.id, 0) + 1

        def get_count(alias):
            name = alias.asname if alias.asname else alias.name
            # If dotted name like 'a.b', look at root
            if '.' in name:
                name = name.split('.')[0]
            return ref_counts.get(name, 0)

        # Sort in descending mention count, then alphabetically as fallback
        return sorted(aliases, key=lambda a: (-get_count(a), a.name))

    def _combine_import(self, node_list, parent):
        alias = []
        namespace = None

        for statement in node_list:
            namespace = statement.namespace
            if isinstance(statement, ast.Import):
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
                        ast.ImportFrom(module=prev_import.module, names=sorted_alias, level=prev_import.level), parent=parent, namespace=prev_import.namespace
                    )
                    alias = []

                yield statement

        if alias:
            sorted_alias = self.sort_aliases(alias, self.module)
            yield self.add_child(
                ast.ImportFrom(module=prev_import.module, names=sorted_alias, level=prev_import.level), parent=parent, namespace=prev_import.namespace
            )

    def suite(self, node_list, parent):
        a = list(self._combine_import(node_list, parent))
        b = list(self._combine_import_from(a, parent))
        return self.clean_suite([self.visit(n) for n in b if n is not None], parent)
