import python_minifier._ast as ast
from python_minifier._ast.annotation import get_parent
from python_minifier.transforms.suite_transformer import SuiteTransformer
from python_minifier.transforms.constant_folding import unparse_expression
from python_minifier.transforms.attr_converter import get_str_value

class SyntaxOptimizations(SuiteTransformer):
    """
    Implement T15 (Type Alias Sweeper), T16 (FStringOptimizer), T17 (TernaryReturnOptimizer), and T18 (IfShortCircuiter).
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_TypeAlias(self, node):
        # Strip PEP 695 type aliases (T15)
        return None

    def visit_JoinedStr(self, node):
        parent = get_parent(node)
        if isinstance(parent, ast.FormattedValue) and parent.format_spec is node:
            return self.generic_visit(node)
        node = self.generic_visit(node)
        # Attempt FStringOptimizer (T16)
        elts = []
        for val in node.values:
            if isinstance(val, (ast.Constant, ast.Str)):
                elts.append(val)
            elif isinstance(val, ast.FormattedValue):
                if val.format_spec is None and val.conversion == -1:
                    if isinstance(val.value, (ast.Constant, ast.Str)) and isinstance(get_str_value(val.value), str):
                        elts.append(val.value)
                    else:
                        parent = get_parent(node)
                        str_call = self.add_child(ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[val.value], keywords=[]), parent=parent, namespace=node.namespace)
                        elts.append(str_call)
                else:
                    return node
            else:
                return node

        if not elts:
            return self.add_child(ast.Str(s=''), parent=get_parent(node), namespace=node.namespace)

        expr = elts[0]
        parent = get_parent(node)
        for right in elts[1:]:
            expr = self.add_child(ast.BinOp(left=expr, op=ast.Add(), right=right), parent=parent, namespace=node.namespace)

        try:
            orig_len = len(unparse_expression(node))
            new_len = len(unparse_expression(expr))
            if new_len < orig_len:
                return expr
        except Exception:
            pass
        return node

    def visit_If(self, node):
        node = self.generic_visit(node)
        # Apply IfShortCircuiter (T18)
        if not node.orelse and len(node.body) == 1:
            stmt = node.body[0]
            if isinstance(stmt, ast.Expr):
                parent = get_parent(node)
                new_value = self.add_child(ast.BoolOp(op=ast.And(), values=[node.test, stmt.value]), parent=parent, namespace=node.namespace)
                return self.add_child(ast.Expr(value=new_value), parent=parent, namespace=node.namespace)
        return node

    def suite(self, node_list, parent):
        visited_list = []
        for node in node_list:
            visited = self.visit(node)
            if visited is not None:
                if isinstance(visited, list):
                    visited_list.extend(visited)
                else:
                    visited_list.append(visited)

        # Apply TernaryReturnOptimizer (T17)
        i = 0
        while i < len(visited_list):
            node = visited_list[i]
            # Case 1: explicit else
            if isinstance(node, ast.If) and len(node.body) == 1 and len(node.orelse) == 1:
                stmt_body = node.body[0]
                stmt_else = node.orelse[0]
                if isinstance(stmt_body, ast.Return) and isinstance(stmt_else, ast.Return):
                    a = stmt_body.value or self.add_child(ast.NameConstant(value=None), parent=parent, namespace=node.namespace)
                    b = stmt_else.value or self.add_child(ast.NameConstant(value=None), parent=parent, namespace=node.namespace)
                    ternary = self.add_child(ast.IfExp(test=node.test, body=a, orelse=b), parent=parent, namespace=node.namespace)
                    new_return = self.add_child(ast.Return(value=ternary), parent=parent, namespace=node.namespace)
                    visited_list[i] = new_return
                    node = new_return

            # Case 2: implicit else
            if i + 1 < len(visited_list):
                next_node = visited_list[i + 1]
                if isinstance(node, ast.If) and not node.orelse and len(node.body) == 1:
                    stmt_body = node.body[0]
                    if isinstance(stmt_body, ast.Return) and isinstance(next_node, ast.Return):
                        a = stmt_body.value or self.add_child(ast.NameConstant(value=None), parent=parent, namespace=node.namespace)
                        b = next_node.value or self.add_child(ast.NameConstant(value=None), parent=parent, namespace=node.namespace)
                        ternary = self.add_child(ast.IfExp(test=node.test, body=a, orelse=b), parent=parent, namespace=node.namespace)
                        new_return = self.add_child(ast.Return(value=ternary), parent=parent, namespace=node.namespace)
                        visited_list[i] = new_return
                        visited_list.pop(i + 1)
                        continue

            i += 1
        return visited_list
