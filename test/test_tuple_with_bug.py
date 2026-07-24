import ast

from python_minifier import unparse
from python_minifier._ast.compare import compare_ast


def test_single_element_tuple_in_with():
    """Test that single-element tuples in with statements are preserved during minification."""

    source = 'with(None,):pass'

    expected_ast = ast.parse(source)
    minified = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(minified))


def test_tuple_with_multiple_elements():
    """Test that multi-element tuples in with statements work correctly."""

    source = 'with(a,b):pass'

    expected_ast = ast.parse(source)
    minified = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(minified))


def test_nested_tuple_with():
    """Test nested tuple structures in with statements."""

    source = 'with((a,),b):pass'

    expected_ast = ast.parse(source)
    minified = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(minified))
