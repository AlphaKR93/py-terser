import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

class RemoveTypeStmt(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    # In Python >= 3.12, ast.TypeAlias represents `type X = ...`
    def visit_TypeAlias(self, node):
        return None
