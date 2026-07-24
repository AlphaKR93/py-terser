import python_minifier._ast as ast
from python_minifier._ast.annotation import get_parent
from python_minifier.transforms.suite_transformer import SuiteTransformer

class DeadCodeEliminator(SuiteTransformer):
    """
    Evaluate compile-time static conditions in If statements and prune/inline branches.
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_If(self, node):
        node.test = self.visit(node.test)

        is_static = False
        val = None
        if isinstance(node.test, ast.NameConstant):
            is_static = True
            val = node.test.value
        elif isinstance(node.test, ast.Num):
            is_static = True
            val = node.test.n
        elif isinstance(node.test, ast.Constant):
            is_static = True
            val = node.test.value

        if is_static:
            parent = get_parent(node)
            truth = bool(val)
            if truth:
                body = self.suite(node.body, parent=parent)
                return body
            else:
                if node.orelse:
                    orelse = self.suite(node.orelse, parent=parent)
                    return orelse
                return None

        node.body = self.suite(node.body, parent=node)
        if node.orelse:
            node.orelse = self.suite(node.orelse, parent=node)
        return node
