import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

class SimplifyPositionArguments(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_arguments(self, node):
        if hasattr(node, 'posonlyargs') and node.posonlyargs:
            node.args = node.posonlyargs + node.args
            node.posonlyargs = []
        return self.generic_visit(node)
