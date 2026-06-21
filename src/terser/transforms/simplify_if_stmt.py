import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer

class SimplifyIfStmt(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_If(self, node):
        node = self.generic_visit(node)
        if not node.orelse and len(node.body) == 1:
            stmt = node.body[0]
            if isinstance(stmt, ast.Expr):
                parent = get_parent(node)
                new_value = self.add_child(
                    ast.BoolOp(op=ast.And(), values=[node.test, stmt.value]),
                    parent=parent,
                    namespace=node.namespace
                )
                return self.add_child(ast.Expr(value=new_value), parent=parent, namespace=node.namespace)
        return node
