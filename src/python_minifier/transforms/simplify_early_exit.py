import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

def has_early_exit(suite):
    if not suite:
        return False
    last = suite[-1]
    if isinstance(last, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
        return True
    if isinstance(last, ast.If) and last.orelse:
        return has_early_exit(last.body) and has_early_exit(last.orelse)
    return False

class SimplifyEarlyExit(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def suite(self, node_list, parent):
        visited_list = []
        for node in node_list:
            visited = self.visit(node)
            if visited is not None:
                if isinstance(visited, list):
                    visited_list.extend(visited)
                else:
                    visited_list.append(visited)

        i = 0
        while i < len(visited_list):
            node = visited_list[i]
            if isinstance(node, ast.If) and node.orelse:
                if has_early_exit(node.body):
                    orelse_visited = self.suite(node.orelse, parent=parent)
                    node.orelse = []
                    visited_list = visited_list[:i+1] + orelse_visited + visited_list[i+1:]
            i += 1
        return visited_list
