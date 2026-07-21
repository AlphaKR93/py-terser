from .ast import CompareError, ast, compare_ast

from .exceptions import InvalidTransformError
from terser._pipeline.printer.module_printer import ModulePrinter
# from terser._pipeline.mangler import (
#     allow_rename_globals,
#     allow_rename_locals,
#     rename,
#     rename_literals,
# )

from ._pipeline.linker import binder
from ._pipeline.parser import parser
from ._pipeline.preprocessor import preprocess
from ._pipeline.transforms import __transforms__
from .config import TransformConfig


def unparse(
    path: str,
    source: str | None,
    module: ast.Module,
    prefer_single_line: bool = False
) -> str:
    """
    Turn a module AST into python code

    This returns an exact representation of the given module,
    such that it can be parsed back into the same AST.

    :param ast.Module module: The module to turn into python code
    :param bool prefer_single_line: If semi-colons should be preferred over newlines where there is no difference in output size
    :rtype: str
    """
    printer = ModulePrinter(prefer_single_line=prefer_single_line)
    printer(module)

    try:
        minified_module = ast.parse(printer.code, 'terser.unparse output')
    except SyntaxError as syntax_error:
        raise InvalidTransformError(syntax_error, path, source, module)

    try:
        compare_ast(module, minified_module)
    except CompareError as compare_error:
        raise InvalidTransformError(compare_error, path, source, minified_module)

    return printer.code


def minify0(
    source: str,
    config: TransformConfig,
    path: str = "<unknown>",
    hoist_literals=True,
    rename_locals=True,
    preserve_locals=None,
    rename_globals=False,
    preserve_globals=None,
    preserve_shebang=True,
    prefer_single_line=False,
):
    """
    Minify a python module

    The module is transformed according to arguments.
    If all transformation arguments are False, no transformations are made to the AST, the returned string will
    parse into exactly the same module.

    Using the default arguments only transformations that are always or almost always safe are enabled.

    :param str source: The python module source code
    :param str path: The original source filename if known

    :param bool hoist_literals: If str and byte literals may be hoisted to the module level where possible.
    :param bool rename_locals: If local names may be shortened
    :param preserve_locals: Locals names to leave unchanged when rename_locals is True
    :type preserve_locals: list[str]
    :param bool rename_globals: If global names may be shortened
    :param preserve_globals: Global names to leave unchanged when rename_globals is True
    :type preserve_globals: list[str]
    :param bool preserve_shebang: Keep any shebang interpreter directive from the source in the minified output
    :param bool prefer_single_line: If semi-colons should be preferred over newlines where there is no difference in output size

    :rtype: str
    """

    source, shebang = preprocess(source, {}, False)
    module, module_ref = parser.parse(source, path)


    for transform in __transforms__:
        module = transform(config)(module)


    binder.resolve(module)
    binder.bind(module)


    if config.remove_empty_exc_brackets and not module_ref.tainted:
        remove_no_arg_exception_call(module)


    if module_ref.tainted:
        rename_globals = False
        rename_locals = False

    if preserve_locals is None:
        preserve_locals = []
    elif isinstance(preserve_locals, str):
        preserve_locals = [preserve_locals]
    if preserve_globals is None:
        preserve_globals = []
    elif isinstance(preserve_globals, str):
        preserve_globals = [preserve_globals]

    preserve_locals.extend(module.preserved)
    preserve_globals.extend(module.preserved)

    allow_rename_locals(module, rename_locals, preserve_locals)
    allow_rename_globals(module, rename_globals, preserve_globals)

    if hoist_literals:
        rename_literals(module)

    rename(module, prefix_globals=not rename_globals, preserved_globals=preserve_globals)


    if config.convert_posargs:
        module = remove_posargs(module)


    try:
        module = ast.parse(module)
    except SyntaxError as exc:
        raise InvalidTransformError(exc, path, source, module) from exc


    minified = unparse(path, source, module, prefer_single_line=prefer_single_line)
    return (shebang + '\n' + minified) if preserve_shebang and shebang else minified
