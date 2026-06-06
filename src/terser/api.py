"""
This module contains the public API for the terser package.
"""

import re
import terser.ast_compat as ast
from terser.ast_annotation import add_parent
from terser.ast_compare import CompareError, compare_ast
from terser.module_printer import ModulePrinter
from terser.rename import (
    add_namespace,
    allow_rename_globals,
    allow_rename_locals,
    bind_names,
    rename,
    rename_literals,
    resolve_names
)
from terser.transforms.combine_imports import CombineImports
from terser.transforms.constant_folding import FoldConstants
from terser.transforms.remove_annotations import RemoveAnnotations
from terser.transforms.remove_type_hints import RemoveTypeHints
from terser.transforms.remove_annotations_options import RemoveAnnotationsOptions
from terser.transforms.remove_asserts import RemoveAsserts
from terser.transforms.remove_debug import RemoveDebug
from terser.transforms.remove_exception_brackets import remove_no_arg_exception_call
from terser.transforms.remove_explicit_return_none import RemoveExplicitReturnNone
from terser.transforms.remove_literal_statements import RemoveDocstrings
from terser.transforms.remove_pass import RemovePass
from terser.transforms.remove_posargs import remove_posargs

from terser.transforms.dead_code_elimination import DeadCodeEliminator
from terser.transforms.decorators_and_contracts import DecoratorsAndContractsSweeper
from terser.transforms.attr_converter import AttrConverter
from terser.transforms.inline_functions import InlineFunctions
from terser.transforms.generic_sweeper import GenericSweeper
from terser.transforms.int_flag_simplifier import IntFlagSimplifier
from terser.transforms.syntax_optimizations import SyntaxOptimizations
from terser.transforms.general_minifications import GeneralMinifications
from terser.transforms.lambda_converter import LambdaConverter
from terser.transforms.early_exit_else_eliminator import EarlyExitElseEliminator
from terser.transforms.dynamic_import_renamer import DynamicImportRenamer
from terser.transforms.local_reference_aliasing import LocalReferenceAliaser


class UnstableMinification(RuntimeError):
    """
    Raised when a minified module differs from the original module in an unexpected way.

    This is raised when the minifier generates source code that doesn't parse back into the
    original module (after known transformations).
    This should never occur and is a bug.
    """

    def __init__(self, exception, source, minified):
        self.exception = exception
        self.source = source
        self.minified = minified

    def __str__(self):
        return 'Minification was unstable! Please create an issue at https://github.com/dflook/python-minifier/issues'


def preprocess_conditional_compilation(source, defines):
    if defines is None:
        defines = {}
    if isinstance(defines, (list, tuple, set)):
        defines = {x: True for x in defines}

    if isinstance(source, bytes):
        source = source.decode('utf-8')

    lines = source.splitlines()
    output_lines = []
    stack = []

    def currently_keeping():
        return all(state[0] for state in stack)

    for line in lines:
        stripped = line.strip()

        # Check block directives
        if re.match(r'^#\s*if\s+(\w+)\s*$', stripped):
            cond = re.match(r'^#\s*if\s+(\w+)\s*$', stripped).group(1)
            parent_ok = currently_keeping()
            is_defined = defines.get(cond, False)
            stack.append((parent_ok and is_defined, is_defined))
            output_lines.append('')
            continue
        elif re.match(r'^#\s*else\s*$', stripped):
            if not stack:
                output_lines.append(line)
                continue
            parent_ok = all(state[0] for state in stack[:-1])
            prev_keep, prev_chosen = stack.pop()
            stack.append((parent_ok and not prev_chosen, True))
            output_lines.append('')
            continue
        elif re.match(r'^#\s*endif\s*$', stripped):
            if not stack:
                output_lines.append(line)
                continue
            stack.pop()
            output_lines.append('')
            continue

        # Check inline directive
        inline_match = re.search(r'\s*#\s*if\s+(\w+)\s*$', line)
        if inline_match:
            cond = inline_match.group(1)
            code_part = line[:inline_match.start()]
            is_defined = defines.get(cond, False)
            if currently_keeping() and is_defined:
                output_lines.append(code_part)
            else:
                output_lines.append('')
        else:
            if currently_keeping():
                output_lines.append(line)
            else:
                output_lines.append('')

    return '\n'.join(output_lines)


def minify(
    source,
    filename=None,
    remove_annotations=RemoveAnnotationsOptions(),
    remove_pass=True,
    remove_literal_statements=False,
    strict=True,
    combine_imports=True,
    hoist_literals=True,
    rename_locals=True,
    preserve_locals=None,
    rename_globals=False,
    preserve_globals=None,
    remove_object_base=True,
    convert_posargs_to_args=True,
    preserve_shebang=True,
    remove_asserts=False,
    remove_debug=False,
    remove_explicit_return_none=True,
    remove_builtin_exception_brackets=True,
    constant_folding=True,
    prefer_single_line=False,
    rename_map=None,
    defines=None,
    obfuscation_map=None,
    module_name_map=None,
    current_module_name=None,
    user_modules=None,
    ignore_all=False,
):
    """
    Minify a python module
    """
    filename = filename or 'terser.minify source'

    source = preprocess_conditional_compilation(source, defines)

    # This will raise if the source file can't be parsed
    module = ast.parse(source, filename)

    add_parent(module)

    if module_name_map:
        import os
        from terser.transforms.module_obfuscator import ImportedNamesCollector, ModuleObfuscator
        
        if not current_module_name and filename:
            base = os.path.basename(filename)
            current_module_name = os.path.splitext(base)[0]
            
        collector = ImportedNamesCollector(current_module_name)
        collector.visit(module)
        
        obfuscator = ModuleObfuscator(module_name_map, current_module_name, collector.imported_modules, user_modules=user_modules)
        module = obfuscator.visit(module)

    add_namespace(module)

    if remove_literal_statements:
        module = RemoveDocstrings(strict=strict)(module)

    if combine_imports:
        module = CombineImports()(module)

    if isinstance(remove_annotations, bool):
        remove_annotations_options = RemoveAnnotationsOptions(
            remove_variable_annotations=remove_annotations,
            remove_return_annotations=remove_annotations,
            remove_argument_annotations=remove_annotations,
            remove_class_attribute_annotations=remove_annotations,
        )
    elif isinstance(remove_annotations, RemoveAnnotationsOptions):
        remove_annotations_options = remove_annotations
    else:
        raise TypeError('remove_annotations must be a bool or RemoveAnnotationsOptions')

    if remove_annotations_options:
        module = RemoveAnnotations(remove_annotations_options)(module)
        module = RemoveTypeHints(remove_annotations_options)(module)

    if remove_asserts or remove_debug:
        module = RemoveAsserts()(module)

    fold_options = {
        'remove_debug': remove_debug,
        'version_info': (3, 12, 0),
        'platform': 'linux'
    }

    if constant_folding:
        add_parent(module)
        add_namespace(module)
        module = FoldConstants(options=fold_options)(module)
        module = DeadCodeEliminator()(module)

    add_parent(module)
    add_namespace(module)
    module = DecoratorsAndContractsSweeper()(module)
    module = AttrConverter()(module)
    module = InlineFunctions()(module)
    module = GenericSweeper()(module)
    module = IntFlagSimplifier()(module)
    module = SyntaxOptimizations()(module)
    module = GeneralMinifications()(module)
    module = LambdaConverter()(module)
    module = EarlyExitElseEliminator()(module)

    if remove_explicit_return_none:
        add_parent(module)
        add_namespace(module)
        module = RemoveExplicitReturnNone()(module)

    if constant_folding:
        add_parent(module)
        add_namespace(module)
        module = FoldConstants(options=fold_options)(module)
        module = DeadCodeEliminator()(module)

    module = LocalReferenceAliaser()(module)

    add_parent(module)
    add_namespace(module)

    bind_names(module)
    resolve_names(module)

    if remove_builtin_exception_brackets and not module.tainted:
        remove_no_arg_exception_call(module)

    if module.tainted:
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

    filtered_preserve_globals = []
    for item in preserve_globals:
        if ':' in item:
            mod_part, name_part = item.split(':', 1)
            if current_module_name == mod_part:
                filtered_preserve_globals.append(name_part)
        else:
            filtered_preserve_globals.append(item)
    preserve_globals = filtered_preserve_globals

    preserve_locals.extend(module.preserved)
    preserve_globals.extend(module.preserved)

    if module_name_map:
        preserve_globals.extend(module_name_map.values())

    allow_rename_locals(module, rename_locals, preserve_locals)
    allow_rename_globals(module, rename_globals, preserve_globals, ignore_all=ignore_all)

    if hoist_literals:
        rename_literals(module)

    rename(module, prefix_globals=not rename_globals, preserved_globals=preserve_globals)

    if isinstance(obfuscation_map, dict):
        from terser.rename.renamer import sorted_bindings
        for _namespace, binding in sorted_bindings(module):
            if binding.original_name and binding.name and binding.name != binding.original_name:
                obfuscation_map[binding.original_name] = binding.name

    # Drop __all__ assignment at final output after renaming is complete
    module.body = [stmt for stmt in module.body if not (
        isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == '__all__'
    )]

    # Update dynamic imports via __import__ or importlib.import_module
    module = DynamicImportRenamer(rename_map)(module)

    if convert_posargs_to_args:
        module = remove_posargs(module)

    if remove_pass:
        module = RemovePass()(module)

    minified = unparse(module, prefer_single_line=prefer_single_line)

    if preserve_shebang is True:
        shebang_line = _find_shebang(source)
        if shebang_line is not None:
            return shebang_line + '\n' + minified

    return minified


def _find_shebang(source):
    """
    Find a shebang line in source
    """
    if isinstance(source, bytes):
        shebang = re.match(br'^#!.*', source)
        if shebang:
            return shebang.group().decode()
    else:
        shebang = re.match(r'^#!.*', source)
        if shebang:
            return shebang.group()

    return None


def unparse(module, prefer_single_line=False):
    """
    Turn a module AST into python code
    """
    assert isinstance(module, ast.Module)

    printer = ModulePrinter(prefer_single_line=prefer_single_line)
    printer(module)

    try:
        minified_module = ast.parse(printer.code, 'terser.unparse output')
    except SyntaxError as syntax_error:
        raise UnstableMinification(syntax_error, '', printer.code)

    try:
        compare_ast(module, minified_module)
    except CompareError as compare_error:
        raise UnstableMinification(compare_error, '', printer.code)

    return printer.code


def awslambda(source, filename=None, entrypoint=None):
    """
    Minify a python module for use as an AWS Lambda function
    """
    rename_globals = True
    if entrypoint is None:
        rename_globals = False

    return minify(
        source, filename, remove_literal_statements=True, rename_globals=rename_globals, preserve_globals=[entrypoint],
    )
