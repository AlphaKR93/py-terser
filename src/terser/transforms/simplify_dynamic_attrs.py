import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer

def get_str_value(node):
    if isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None

class SimplifyDynamicAttributes(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        # getattr(obj, "foo") -> obj.foo
        if isinstance(node.func, ast.Name) and node.func.id == 'getattr' and len(node.args) == 2:
            obj = node.args[0]
            attr_node = node.args[1]
            attr_name = get_str_value(attr_node)
            if attr_name and attr_name.isidentifier() and not attr_name.startswith('__'):
                return self.add_child(ast.Attribute(value=obj, attr=attr_name, ctx=ast.Load()), parent=get_parent(node), namespace=node.namespace)

        # Clazz.__getattr__(obj, "foo") -> obj.foo
        if isinstance(node.func, ast.Attribute) and node.func.attr == '__getattr__' and len(node.args) == 2:
            clazz = node.func.value
            obj = node.args[0]
            attr_node = node.args[1]
            attr_name = get_str_value(attr_node)
            if attr_name and attr_name.isidentifier() and not attr_name.startswith('__'):
                # Statically check if obj matches clazz name or class annotations (if any exists)
                # For safety, only do this if obj is a Name and matches clazz Name
                if isinstance(obj, ast.Name) and isinstance(clazz, ast.Name) and obj.id == clazz.id:
                    return self.add_child(ast.Attribute(value=obj, attr=attr_name, ctx=ast.Load()), parent=get_parent(node), namespace=node.namespace)

        return node

    def visit_Expr(self, node):
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Call):
            # setattr(obj, "foo", val) -> obj.foo = val
            if isinstance(node.value.func, ast.Name) and node.value.func.id == 'setattr' and len(node.value.args) == 3:
                obj = node.value.args[0]
                attr_node = node.value.args[1]
                val = node.value.args[2]
                attr_name = get_str_value(attr_node)
                if attr_name and attr_name.isidentifier() and not attr_name.startswith('__'):
                    parent = get_parent(node)
                    new_target = self.add_child(ast.Attribute(value=obj, attr=attr_name, ctx=ast.Store()), parent=parent, namespace=node.namespace)
                    return self.add_child(ast.Assign(targets=[new_target], value=val), parent=parent, namespace=node.namespace)

            # Clazz.__setattr__(obj, "foo", val) -> obj.foo = val
            if isinstance(node.value.func, ast.Attribute) and node.value.func.attr == '__setattr__' and len(node.value.args) == 3:
                clazz = node.value.func.value
                obj = node.value.args[0]
                attr_node = node.value.args[1]
                val = node.value.args[2]
                attr_name = get_str_value(attr_node)
                if attr_name and attr_name.isidentifier() and not attr_name.startswith('__'):
                    if isinstance(obj, ast.Name) and isinstance(clazz, ast.Name) and obj.id == clazz.id:
                        parent = get_parent(node)
                        new_target = self.add_child(ast.Attribute(value=obj, attr=attr_name, ctx=ast.Store()), parent=parent, namespace=node.namespace)
                        return self.add_child(ast.Assign(targets=[new_target], value=val), parent=parent, namespace=node.namespace)
        return node
