import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer

def get_str_value(node):
    if isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None

class AttrConverter(SuiteTransformer):
    """
    Convert getattr(obj, "name") -> obj.name and setattr(obj, "name", val) -> obj.name = val.
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == 'getattr' and len(node.args) == 2:
            obj = node.args[0]
            attr_node = node.args[1]
            attr_name = get_str_value(attr_node)
            if attr_name and attr_name.isidentifier() and not attr_name.startswith('__'):
                return self.add_child(ast.Attribute(value=obj, attr=attr_name, ctx=ast.Load()), parent=get_parent(node), namespace=node.namespace)
        return node

    def visit_Expr(self, node):
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'setattr':
            args = node.value.args
            if len(args) == 3:
                obj = args[0]
                attr_node = args[1]
                val = args[2]
                attr_name = get_str_value(attr_node)
                if attr_name and attr_name.isidentifier() and not attr_name.startswith('__'):
                    parent = get_parent(node)
                    new_target = self.add_child(ast.Attribute(value=obj, attr=attr_name, ctx=ast.Store()), parent=parent, namespace=node.namespace)
                    return self.add_child(ast.Assign(targets=[new_target], value=val), parent=parent, namespace=node.namespace)
        return node
