import terser.ast_compat as ast
from terser.transforms.suite_transformer import SuiteTransformer
from terser.transforms.attr_converter import get_str_value

class DynamicImportRenamer(SuiteTransformer):
    """
    Update dynamic imports via __import__ or importlib.import_module with obfuscated names.
    """
    def __init__(self, rename_map=None):
        super(DynamicImportRenamer, self).__init__()
        self.rename_map = rename_map or {}

    def __call__(self, node):
        if not self.rename_map:
            return node
        return self.visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        # Check __import__("name")
        if isinstance(node.func, ast.Name) and node.func.id == '__import__' and node.args:
            val = get_str_value(node.args[0])
            if val in self.rename_map:
                node.args[0] = self.add_child(ast.Str(s=self.rename_map[val]), parent=node, namespace=node.namespace)
        # Check importlib.import_module("name")
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'importlib' and node.args:
            val = get_str_value(node.args[0])
            if val in self.rename_map:
                node.args[0] = self.add_child(ast.Str(s=self.rename_map[val]), parent=node, namespace=node.namespace)
        return node
