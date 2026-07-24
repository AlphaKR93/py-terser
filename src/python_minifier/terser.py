from concurrent.futures import ThreadPoolExecutor

from ._ast import ast, tree as _ast
from .config import TerserConfig
from .preprocessor import preprocess
from ._utils.progress import ProgressReporter

if __debug__ and __import__("typing").TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


SOURCE_EXTENSIONS = (".py", ".pyw",)


def minify(
    source: str,
    config: TerserConfig,
    filename: str | None = None,
):
    """
    Minify a python module (Backwards compatible routing wrapper).
    """

    filename = filename or 'python_minifier.minify source'
    if current_module_name is None and filename and filename != 'python_minifier.minify source':
        import os
        abs_path = os.path.abspath(filename)
        dirname, basename = os.path.split(abs_path)
        name, ext = os.path.splitext(basename)
        parts = [name]
        curr_dir = dirname
        while curr_dir:
            if os.path.exists(os.path.join(curr_dir, '__init__.py')):
                parent_dir, dir_name = os.path.split(curr_dir)
                if not dir_name:
                    break
                parts.insert(0, dir_name)
                curr_dir = parent_dir
            else:
                break
        current_module_name = '.'.join(parts)

    # Instantiate config
    config = TerserConfig(
        threads=threads,
        transform_passes=transform_passes,
        fold_constants=constant_folding,
        optimize=optimize,
        defines=defines or {},
        remove_docstrings=remove_literal_statements,
        strict_docstrings=strict,
        remove_annotations=remove_ann,
        remove_variable_annotations=remove_var_ann,
        remove_return_annotations=remove_ret_ann,
        remove_argument_annotations=remove_arg_ann,
        remove_class_attribute_annotations=remove_cls_ann,
        remove_explicit_inherits=remove_object_base,
        remove_type_stmt=remove_type_stmt,
        remove_trailing_returns=remove_explicit_return_none,
        simplify_posargs=convert_posargs_to_args,
        simplify_dynamic_attrs=simplify_dynamic_attrs,
        simplify_fstring=simplify_fstring,
        simplify_early_exit=simplify_early_exit,
        simplify_raise=remove_builtin_exception_brackets,
        simplify_if_stmt=simplify_if_stmt,
        convert_to_ternary=convert_to_ternary,
        convert_to_lambda=convert_to_lambda,
        hoist_literals=hoist_literals,
        inline_functions=inline_functions,
        inline_int_flags=inline_int_flags,
        cleanup_imports=combine_imports,
        rename_locals=rename_locals,
        rename_globals=rename_globals,
        preserve_locals=preserve_locals or [],
        preserve_globals=preserve_globals or [],
        ignore_all=ignore_all,
        prefer_single_line=prefer_single_line,
        preserve_shebang=preserve_shebang,
        obfuscation_map=obfuscation_map,
        rename_map=rename_map,
        module_name_map=module_name_map,
        current_module_name=current_module_name,
        user_modules=user_modules or set()
    )

    pipeline = Pipeline(config)
    result = pipeline.run_source(source, filename)
    return result.code

def unparse(module, prefer_single_line=False):
    import python_minifier._ast as ast
    from python_minifier.printer.module_printer import ModulePrinter
    from python_minifier._ast.compare import CompareError, compare_ast

    assert isinstance(module, ast.Module)
    printer = ModulePrinter(prefer_single_line=prefer_single_line)
    printer(module)

    try:
        minified_module = ast.parse(printer.code, 'python_minifier.unparse output')
    except SyntaxError as syntax_error:
        raise UnstableMinification(syntax_error, '', printer.code)

    try:
        compare_ast(module, minified_module)
    except CompareError as compare_error:
        raise UnstableMinification(compare_error, '', printer.code)

    return printer.code
