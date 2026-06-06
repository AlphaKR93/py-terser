import terser.ast_compat as ast
from terser.transforms.suite_transformer import SuiteTransformer
from terser.util import is_constant_node

def find_doc(node):
    if isinstance(node, ast.Attribute) and node.attr == '__doc__':
        raise ValueError('__doc__ found!')
    for child in ast.iter_child_nodes(node):
        find_doc(child)

def _doc_in_module(module):
    try:
        find_doc(module)
        return False
    except Exception:
        return True

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
    """
    Remove docstrings from modules, classes, and functions.
    """

    def __init__(self, strict=True):
        super(RemoveDocstrings, self).__init__()
        self.strict = strict

    def __call__(self, node):
        self.doc_referenced = _doc_in_module(node)
        return self.visit(node)

    def is_docstring_node(self, node, suite, parent):
        if not suite or suite[0] is not node:
            return False
        if not isinstance(node, ast.Expr):
            return False
        if not is_constant_node(node.value, (ast.Str, ast.Bytes)):
            return False

        # It's the first statement in a suite, and it is a string/bytes constant.
        if isinstance(parent, ast.Module):
            if not self.strict:
                # If strict is False, always remove module docstrings
                return True
            else:
                # If strict is True, only preserve if __doc__ is referenced in the module
                return not self.doc_referenced

        if isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if has_preserve_docstring_decorator(parent):
                return False
            return True

        return False

    def suite(self, node_list, parent):
        clean_nodes = self.clean_suite([self.visit(n) for n in node_list if n is not None and not self.is_docstring_node(n, node_list, parent)], parent)

        if len(clean_nodes) == 0:
            if isinstance(parent, ast.Module):
                return []
            else:
                return [self.add_child(ast.Expr(value=ast.Num(0)), parent=parent)]

        return clean_nodes

RemoveLiteralStatements = RemoveDocstrings
