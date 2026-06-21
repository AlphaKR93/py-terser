import terser._ast as ast
from terser.transforms.suite_transformer import SuiteTransformer

class RemoveTrailingReturns(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_FunctionDef(self, node):
        node.args = self.visit(node.args)
        node.body = self.suite(node.body, parent=node)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]

        if node.body:
            last_stmt = node.body[-1]
            if isinstance(last_stmt, ast.Return):
                is_none = False
                if last_stmt.value is None:
                    is_none = True
                elif isinstance(last_stmt.value, ast.NameConstant) and last_stmt.value.value is None:
                    is_none = True
                elif isinstance(last_stmt.value, ast.Constant) and last_stmt.value.value is None:
                    is_none = True
                elif isinstance(last_stmt.value, ast.Name) and last_stmt.value.id == 'None':
                    is_none = True
                
                if is_none:
                    node.body.pop()

        if not node.body:
            node.body = [self.add_child(ast.Expr(value=ast.Num(0)), parent=node)]

        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)
