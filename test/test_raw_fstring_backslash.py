"""
Test for raw f-string with backslash escape sequences.
"""

import ast
import sys

import pytest

from terser import unparse
from terser._ast.compare import compare_ast


@pytest.mark.parametrize(('source', 'description'), [
    # Raw f-string backslash tests - core regression fix
    pytest.param(r'rf"{x:\\xFF}"', 'Single backslash in format spec (minimal failing case)', id='raw-fstring-backslash-format-spec'),
    pytest.param(r'rf"\\n{x}\\t"', 'Backslashes in literal parts', id='raw-fstring-backslash-outer-str'),
    pytest.param(r'rf"\\n{x:\\xFF}\\t"', 'Backslashes in both literal and format spec', id='raw-fstring-mixed-backslashes'),
    pytest.param(r'rf"\n"', 'Single backslash in literal only', id='raw-fstring-literal-single-backslash'),
    pytest.param(r'rf"\\n"', 'Double backslash in literal only', id='raw-fstring-literal-double-backslash'),
    pytest.param(r'rf"{x:\xFF}"', 'Single backslash in format spec only', id='raw-fstring-formatspec-single-backslash'),
    pytest.param(r'rf"{x:\\xFF}"', 'Double backslash in format spec only', id='raw-fstring-formatspec-double-backslash'),
    pytest.param(r'rf"\n{x:\xFF}\t"', 'Single backslashes in both parts', id='raw-fstring-mixed-single-backslashes'),

    # Special characters discovered during fuzzing
    pytest.param('f"test\\x00end"', 'Null byte in literal part', id='null-byte-literal'),
    pytest.param('f"{x:\\x00}"', 'Null byte in format spec', id='null-byte-format-spec'),
    pytest.param('f"test\\rend"', 'Carriage return in literal (must be escaped to prevent semantic changes)', id='carriage-return-literal'),
    pytest.param('f"test\\tend"', 'Tab in literal part', id='tab-literal'),
    pytest.param('f"{x:\\t}"', 'Tab in format spec', id='tab-format-spec'),
    pytest.param('f"test\\x01end"', 'Control character (ASCII 1)', id='control-character'),
    pytest.param('f"test\\nend"', 'Newline in single-quoted string', id='newline-single-quote'),
    pytest.param('f"""test\nend"""', 'Actual newline in triple-quoted string', id='newline-triple-quote'),
    pytest.param('f"\\x00\\r\\t{x}"', 'Mix of null bytes, carriage returns, and tabs', id='mixed-special-chars'),

    # Conversion specifiers with special characters
    pytest.param(r'rf"{x!r:\\xFF}"', 'Conversion specifier !r with format spec', id='conversion-r-with-backslash'),
    pytest.param(r'rf"{x!s:\\xFF}"', 'Conversion specifier !s with format spec', id='conversion-s-with-backslash'),
    pytest.param(r'rf"{x!a:\\xFF}"', 'Conversion specifier !a with format spec', id='conversion-a-with-backslash'),
    pytest.param('f"{x!r:\\x00}"', 'Conversion specifier with null byte in format spec', id='conversion-with-null-byte'),

    # Other edge cases
    pytest.param(r'rf"""{x:\\xFF}"""', 'Triple-quoted raw f-string with backslashes', id='raw-fstring-triple-quoted'),
    pytest.param(r'rf"{x:\\xFF}{y:\\xFF}"', 'Multiple interpolations with backslashes', id='raw-fstring-multiple-interpolations'),
    pytest.param('f"\\\\n{x}\\\\t"', 'Regular (non-raw) f-string with backslashes', id='regular-fstring-with-backslash'),
])
@pytest.mark.skipif(sys.version_info < (3, 6), reason='F-strings not supported in Python < 3.6')
def test_fstring_edge_cases(source, description):
    """Test f-strings with various edge cases including backslashes and special characters."""
    expected_ast = ast.parse(source)
    actual_code = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(actual_code))


@pytest.mark.parametrize(('source', 'description'), [
    pytest.param(r'f"{f"\\n{x}\\t"}"', 'Nested f-strings with backslashes in inner string parts', id='nested-fstring-backslashes'),
    pytest.param(r'f"{rf"\\xFF{y}\\n"}"', 'Nested raw f-strings with backslashes', id='nested-raw-fstring-backslashes'),
    pytest.param(r'f"{f"{x:\\xFF}"}"', 'Nested f-strings with backslashes in format specs', id='nested-fstring-format-spec-backslashes'),
])
@pytest.mark.skipif(sys.version_info < (3, 12), reason='Nested f-strings not supported in Python < 3.12')
def test_nested_fstring_edge_cases(source, description):
    """Test nested f-strings with backslashes (Python 3.12+ only)."""
    expected_ast = ast.parse(source)
    actual_code = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(actual_code))


@pytest.mark.skipif(sys.version_info < (3, 6), reason='F-strings not supported in Python < 3.6')
def test_fstring_carriage_return_format_spec():
    r"""Test f-string with carriage return in format spec.

    Note: This is syntactically valid but will fail at runtime with
    ValueError: Unknown format code '\xd' for object of type 'int'
    However, the minifier correctly escapes the carriage return to prevent
    Python from normalizing it to a newline during parsing.
    """
    source = 'f"{x:\\r}"'
    expected_ast = ast.parse(source)
    actual_code = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(actual_code))
