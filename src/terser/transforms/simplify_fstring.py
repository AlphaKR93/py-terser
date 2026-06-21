import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer
from terser.transforms.constant_folding import unparse_expression
from terser.transforms.attr_converter import get_str_value

class SimplifyFString(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_JoinedStr(self, node):
        parent = get_parent(node)
        if isinstance(parent, ast.FormattedValue) and parent.format_spec is node:
            return self.generic_visit(node)

        node = self.generic_visit(node)
        elts = []
        for val in node.values:
            if isinstance(val, (ast.Constant, ast.Str)):
                elts.append(val)
            elif isinstance(val, ast.FormattedValue):
                if val.format_spec is None and val.conversion == -1:
                    # Check if val.value is already a string constant/literal
                    str_val = get_str_value(val.value)
                    if str_val is not None:
                        elts.append(val.value)
                    else:
                        str_call = self.add_child(
                            ast.Call(func=ast.Name(id='str', ctx=ast.Load()), args=[val.value], keywords=[]),
                            parent=parent,
                            namespace=node.namespace
                        )
                        elts.append(str_call)
                else:
                    return node
            else:
                return node

        # Merge adjacent string constants/literals
        merged_elts = []
        for e in elts:
            if merged_elts and isinstance(e, (ast.Constant, ast.Str)) and isinstance(merged_elts[-1], (ast.Constant, ast.Str)):
                # Merge the string values
                val1 = get_str_value(merged_elts[-1])
                val2 = get_str_value(e)
                if isinstance(val1, str) and isinstance(val2, str):
                    merged_elts[-1] = self.add_child(ast.Constant(value=val1 + val2), parent=parent)
                    continue
            merged_elts.append(e)

        if not merged_elts:
            return self.add_child(ast.Constant(value=''), parent=get_parent(node), namespace=node.namespace)

        expr = merged_elts[0]
        for right in merged_elts[1:]:
            expr = self.add_child(ast.BinOp(left=expr, op=ast.Add(), right=right), parent=parent, namespace=node.namespace)

        try:
            orig_len = len(unparse_expression(node))
            new_len = len(unparse_expression(expr))
            if new_len <= orig_len:
                return expr
        except Exception:
            pass
        return node
