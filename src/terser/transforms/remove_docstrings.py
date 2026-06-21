import terser._ast as ast
from terser.transforms.suite_transformer import SuiteTransformer
from terser.util import is_constant_node

def check_decorator_name(dec):
    if isinstance(dec, ast.Call):
        dec = dec.func
    if isinstance(dec, ast.Name):
        return dec.id == 'preserve_docstring'
    if isinstance(dec, ast.Attribute):
        return dec.attr == 'preserve_docstring'
    return False

def has_preserve_docstring_decorator(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    return any(check_decorator_name(dec) for dec in node.decorator_list)

class RemoveDocstrings(SuiteTransformer):
    def __init__(self, strict=True):
        super().__init__()
        self.strict = strict

    def __call__(self, node):
        return self.visit(node)

    def is_docstring_node(self, node, suite, parent):
        if not suite or suite[0] is not node:
            return False
        if not isinstance(node, ast.Expr):
            return False
        if not is_constant_node(node.value, (ast.Str, ast.Bytes, ast.Constant)):
            return False

        # If it is an ast.Constant, it must be a string or bytes
        if isinstance(node.value, ast.Constant) and not isinstance(node.value.value, (str, bytes)):
            return False

        if isinstance(parent, ast.Module):
            # strict=True: preserve module-level docstring
            # strict=False: remove module-level docstring
            return not self.strict

        if isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if has_preserve_docstring_decorator(parent):
                return False
            return True

        return False

    def suite(self, node_list, parent):
        clean_nodes = self.clean_suite([
            self.visit(n) for n in node_list 
            if n is not None and not self.is_docstring_node(n, node_list, parent)
        ], parent)

        if len(clean_nodes) == 0:
            if isinstance(parent, ast.Module):
                return []
            else:
                return [self.add_child(ast.Expr(value=ast.Num(0)), parent=parent)]

        return clean_nodes
