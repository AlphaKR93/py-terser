import terser._ast as ast
from terser.transforms.suite_transformer import SuiteTransformer
from terser._ast.annotation import add_parent as set_parent
from terser.rename.mapper import add_parent as set_namespace

def replace_typevars_with_dummy(node, transformer):
    if isinstance(node, ast.Name):
        if node.id not in {'str', 'int', 'float', 'bool', 'bytes', 'dict', 'list', 'set', 'tuple', 'None', 'Any', 'object'}:
            if node.id.startswith('_terser_T'):
                return node
            local_map = getattr(transformer, 'local_tv_map', None)
            if local_map is not None:
                if node.id in local_map:
                    return ast.Name(id=local_map[node.id], ctx=ast.Load())
                tv_name = f'_terser_T{transformer.typevar_count}'
                transformer.typevar_count += 1
                local_map[node.id] = tv_name
                return ast.Name(id=tv_name, ctx=ast.Load())
            tv_name = f'_terser_T{transformer.typevar_count}'
            transformer.typevar_count += 1
            return ast.Name(id=tv_name, ctx=ast.Load())
        return node
    if isinstance(node, ast.Tuple):
        node.elts = [replace_typevars_with_dummy(elt, transformer) for elt in node.elts]
        return node
    return node

class RemoveGenerics(SuiteTransformer):
    def __init__(self):
        super().__init__()
        self.typevar_count = 0
        self.local_tv_map = None

    def __call__(self, node):
        has_terser_tv = False
        if isinstance(node, ast.Module):
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.module == 'typing':
                    for name in stmt.names:
                        if name.asname == '_terser_tv':
                            has_terser_tv = True
                            break
        res = self.visit(node)
        if not has_terser_tv and self.typevar_count > 0 and isinstance(res, ast.Module):
            insert_idx = 0
            body_len = len(res.body)
            if body_len > 0 and isinstance(res.body[0], ast.Expr) and isinstance(res.body[0].value, ast.Constant) and isinstance(res.body[0].value.value, str):
                insert_idx = 1
            while insert_idx < body_len:
                stmt = res.body[insert_idx]
                if isinstance(stmt, ast.ImportFrom) and stmt.module == '__future__':
                    insert_idx += 1
                else:
                    break

            import_node = ast.ImportFrom(
                module='typing',
                names=[ast.alias(name='TypeVar', asname='_terser_tv')],
                level=0
            )
            set_parent(import_node, parent=res)
            set_namespace(import_node, namespace=res)
            res.body.insert(insert_idx, import_node)
            for i in range(self.typevar_count):
                assign_node = ast.Assign(
                    targets=[ast.Name(id=f'_terser_T{i}', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id='_terser_tv', ctx=ast.Load()),
                        args=[ast.Constant(value=f'_terser_T{i}')],
                        keywords=[]
                    )
                )
                set_parent(assign_node, parent=res)
                set_namespace(assign_node, namespace=res)
                res.body.insert(insert_idx + 1 + i, assign_node)
        return res

    def visit_ClassDef(self, node):
        has_type_params = False
        if hasattr(node, 'type_params') and node.type_params:
            node.type_params = []
            has_type_params = True
        new_bases = []
        self.local_tv_map = {}
        for b in node.bases:
            if isinstance(b, ast.Subscript):
                b.slice = replace_typevars_with_dummy(b.slice, self)
            new_bases.append(b)
        self.local_tv_map = None
        node.bases = new_bases
        node = self.generic_visit(node)
        if has_type_params:
            getitem_node = ast.FunctionDef(
                name='__class_getitem__',
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg='cls'), ast.arg(arg='item')],
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[]
                ),
                body=[ast.Return(value=ast.Name(id='cls', ctx=ast.Load()))],
                decorator_list=[ast.Name(id='classmethod', ctx=ast.Load())]
            )
            set_parent(getitem_node, parent=node)
            set_namespace(getitem_node, namespace=node)
            node.body.insert(0, getitem_node)
        return node

    def visit_FunctionDef(self, node):
        if hasattr(node, 'type_params') and node.type_params:
            node.type_params = []
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

