import python_minifier.ast as ast

from python_minifier.transforms.suite_transformer import SuiteTransformer


class RemoveInlineFunctions(SuiteTransformer):
    """
    Remove or simplify type annotations from source to reduce code size.
    """

    def __init__(self):
        super(RemoveInlineFunctions, self).__init__()

    def visit_Call(self, node):
        is_cast = False
        if isinstance(node.func, ast.Name) and node.func.id == "cast":
            is_cast = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "cast":
            is_cast = True

        if is_cast and len(node.args) == 2 and not node.keywords:
            return self.visit(node.args[1])

        return self.generic_visit(node)
