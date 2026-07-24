"""
Test for raw t-string with backslash escape sequences.

This test covers the same scenarios as test_raw_fstring_backslash.py but for t-strings.
Since t-strings were introduced in Python 3.14 and the raw f-string regression was fixed
in Python 3.14rc2, these tests verify that raw t-strings handle backslashes correctly
from the start, especially in format specs.
"""

import ast
import sys

import pytest

from python_minifier import unparse
from python_minifier._ast.compare import compare_ast


@pytest.mark.parametrize(('source', 'description'), [
    # Raw t-string backslash tests - core regression testing
    pytest.param(r'rt"{x:\\xFF}"', 'Single backslash in format spec (minimal case)', id='raw-tstring-backslash-format-spec'),
    pytest.param(r'rt"\\n{x}\\t"', 'Backslashes in literal parts', id='raw-tstring-backslash-outer-str'),
    pytest.param(r'rt"\\n{x:\\xFF}\\t"', 'Backslashes in both literal and format spec', id='raw-tstring-mixed-backslashes'),
    pytest.param(r'rt"\n"', 'Single backslash in literal only', id='raw-tstring-literal-single-backslash'),
    pytest.param(r'rt"\\n"', 'Double backslash in literal only', id='raw-tstring-literal-double-backslash'),
    pytest.param(r'rt"{x:\xFF}"', 'Single backslash in format spec only', id='raw-tstring-formatspec-single-backslash'),
    pytest.param(r'rt"{x:\\xFF}"', 'Double backslash in format spec only', id='raw-tstring-formatspec-double-backslash'),
    pytest.param(r'rt"\n{x:\xFF}\t"', 'Single backslashes in both parts', id='raw-tstring-mixed-single-backslashes'),

    # Special characters discovered during fuzzing
    pytest.param('t"test\\x00end"', 'Null byte in literal part', id='null-byte-literal'),
    pytest.param('t"{x:\\x00}"', 'Null byte in format spec', id='null-byte-format-spec'),
    pytest.param('t"test\\rend"', 'Carriage return in literal (must be escaped to prevent semantic changes)', id='carriage-return-literal'),
    pytest.param('t"test\\tend"', 'Tab in literal part', id='tab-literal'),
    pytest.param('t"{x:\\t}"', 'Tab in format spec', id='tab-format-spec'),
    pytest.param('t"test\\x01end"', 'Control character (ASCII 1)', id='control-character'),
    pytest.param('t"test\\nend"', 'Newline in single-quoted string', id='newline-single-quote'),
    pytest.param('t"""test\nend"""', 'Actual newline in triple-quoted string', id='newline-triple-quote'),
    pytest.param('t"\\x00\\r\\t{x}"', 'Mix of null bytes, carriage returns, and tabs', id='mixed-special-chars'),

    # Conversion specifiers with special characters
    pytest.param(r'rt"{x!r:\\xFF}"', 'Conversion specifier !r with format spec', id='conversion-r-with-backslash'),
    pytest.param(r'rt"{x!s:\\xFF}"', 'Conversion specifier !s with format spec', id='conversion-s-with-backslash'),
    pytest.param(r'rt"{x!a:\\xFF}"', 'Conversion specifier !a with format spec', id='conversion-a-with-backslash'),
    pytest.param('t"{x!r:\\x00}"', 'Conversion specifier with null byte in format spec', id='conversion-with-null-byte'),

    # Other edge cases
    pytest.param(r'rt"""{x:\\xFF}"""', 'Triple-quoted raw t-string with backslashes', id='raw-tstring-triple-quoted'),
    pytest.param(r'rt"{x:\\xFF}{y:\\xFF}"', 'Multiple interpolations with backslashes', id='raw-tstring-multiple-interpolations'),
    pytest.param('t"\\\\n{x}\\\\t"', 'Regular (non-raw) t-string with backslashes', id='regular-tstring-with-backslash'),

    # Complex format specs - originally in test_raw_tstring_complex_format_specs
    pytest.param(r'rt"{x:\\xFF\\n}"', 'Multiple backslashes in single format spec', id='complex-multiple-backslashes'),
    pytest.param(r'rt"{x:\\xFF}{y:\\n}"', 'Multiple format specs with backslashes', id='complex-multiple-format-specs'),
    pytest.param(r'rt"\\start{x:\\xFF}\\end"', 'Backslashes in both literal and format spec parts', id='complex-mixed-locations'),
    pytest.param(r'rt"{x:{fmt:\\n}}"', 'Nested format spec with backslashes', id='complex-nested-format-spec'),

    # Unicode escapes - originally in test_raw_tstring_unicode_escapes
    pytest.param(r'rt"{x:\u0041}"', 'Unicode escape in format spec', id='unicode-short-escape'),
    pytest.param(r'rt"{x:\U00000041}"', 'Long Unicode escape in format spec', id='unicode-long-escape'),
    pytest.param(r'rt"\\u0041{x:\xFF}"', 'Unicode in literal, hex in format spec', id='unicode-mixed'),

    # Mixed t-string and f-string
    pytest.param(r'rt"t-string \\n {f"f-string {x:\\xFF}"} \\t"', 'Nested combination of raw t-strings and f-strings', id='mixed-tstring-fstring'),
])
@pytest.mark.skipif(sys.version_info < (3, 14), reason='T-strings not supported in Python < 3.14')
def test_tstring_edge_cases(source, description):
    """Test t-strings with various edge cases including backslashes and special characters."""
    expected_ast = ast.parse(source)
    actual_code = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(actual_code))


@pytest.mark.parametrize(('source', 'description'), [
    pytest.param(r't"{t"\\n{x}\\t"}"', 'Nested t-strings with backslashes in inner string parts', id='nested-tstring-backslashes'),
    pytest.param(r't"{rt"\\xFF{y}\\n"}"', 'Nested raw t-strings with backslashes', id='nested-raw-tstring-backslashes'),
    pytest.param(r't"{t"{x:\\xFF}"}"', 'Nested t-strings with backslashes in format specs', id='nested-tstring-format-spec-backslashes'),
])
@pytest.mark.skipif(sys.version_info < (3, 14), reason='T-strings not supported in Python < 3.14')
def test_nested_tstring_edge_cases(source, description):
    """Test nested t-strings with backslashes."""
    expected_ast = ast.parse(source)
    actual_code = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(actual_code))


@pytest.mark.skipif(sys.version_info < (3, 14), reason='T-strings not supported in Python < 3.14')
def test_tstring_carriage_return_format_spec():
    r"""Test t-string with carriage return in format spec.

    Note: This is syntactically valid but will fail at runtime with
    ValueError: Unknown format code '\xd' for object of type 'int'
    However, unlike f-strings, t-strings can successfully unparse this case.
    """
    source = 't"{x:\\r}"'
    expected_ast = ast.parse(source)
    actual_code = unparse(expected_ast)
    compare_ast(expected_ast, ast.parse(actual_code))
