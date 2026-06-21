from __future__ import print_function

import argparse
import os
import sys
import json
from importlib import metadata

from terser.terser import minify
from terser.transforms.remove_annotations_options import RemoveAnnotationsOptions

version = metadata.version('py-terser')

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


class MinificationNotBeneficialError(Exception):
    """Raised when minification results in larger output than the original."""


def stdout_write_bytes(data):
    """Write bytes to stdout with proper compatibility."""
    sys.stdout.buffer.write(data)


def main():
    """
    examples:
        # Minifying stdin to stdout
        terser -

        # Minifying a file to stdout
        terser example.py

        # Minifying a file and writing to a different file
        terser example.py --output example.min.py

        # Minifying a file in place
        terser example.py --in-place

        # Minifying all *.py files in a directory
        terser src/ --in-place

        # Minifying multiple paths in place
        terser file1.py file2.py src/ --in-place
    """
    args = _parse_args()

    # 1. Process stdin
    if len(args.path) == 1 and args.path[0] == "-":
        source = sys.stdin.buffer.read()
        obfuscation_map = {}
        try:
            minified = do_minify(source, 'stdin', args, obfuscation_map, module_name_map={})
        except MinificationNotBeneficialError:
            if args.output:
                with open(args.output, 'wb') as f:
                    f.write(source)
            else:
                stdout_write_bytes(source)
            return

        if args.obfuscation_map:
            all_mappings = {
                "modules": {},
                "files": {"stdin": obfuscation_map}
            }
            path_to_write = args.obfuscation_map
            if os.path.isdir(path_to_write):
                path_to_write = os.path.join(path_to_write, 'obfuscation_map.json')
            with open(path_to_write, 'w', encoding='utf-8') as f:
                json.dump(all_mappings, f, indent=2)

        if args.output:
            with open(args.output, 'wb') as f:
                f.write(minified)
        else:
            stdout_write_bytes(minified)

    # 2. Process multiple files / directory via the core API
    else:
        from terser import minify_project
        minify_project(
            search_paths=args.path,
            output=args.output,
            in_place=args.in_place,
            obfuscation_map_file=args.obfuscation_map,
            no_tree_shake=args.no_tree_shake,
            threads=args.threads,
            transform_passes=args.transform_passes,
            combine_imports=args.combine_imports,
            remove_pass=args.remove_pass,
            remove_literal_statements=args.remove_literal_statements,
            strict=args.strict_docstrings if hasattr(args, 'strict_docstrings') else True,
            remove_annotations=args.remove_annotations,
            remove_variable_annotations=args.remove_variable_annotations,
            remove_return_annotations=args.remove_return_annotations,
            remove_argument_annotations=args.remove_argument_annotations,
            remove_class_attribute_annotations=args.remove_class_attribute_annotations,
            hoist_literals=args.hoist_literals,
            rename_locals=args.rename_locals,
            preserve_locals=args.preserve_locals,
            rename_globals=args.rename_globals,
            preserve_globals=args.preserve_globals,
            remove_object_base=args.remove_object_base,
            convert_posargs_to_args=args.convert_posargs_to_args,
            preserve_shebang=args.preserve_shebang,
            optimize=args.optimize,
            remove_explicit_return_none=args.remove_explicit_return_none,
            remove_builtin_exception_brackets=args.remove_exception_brackets,
            constant_folding=args.constant_folding,
            prefer_single_line=args.prefer_single_line,
            rename_map=None,
            defines=args.defines,
            ignore_all=args.ignore_all,
            remove_type_stmt=args.remove_type_stmt,
            simplify_dynamic_attrs=args.simplify_dynamic_attrs,
            simplify_fstring=args.simplify_fstring,
            simplify_early_exit=args.simplify_early_exit,
            simplify_if_stmt=args.simplify_if_stmt,
            convert_to_ternary=args.convert_to_ternary,
            convert_to_lambda=args.convert_to_lambda,
            inline_functions=args.inline_functions,
            inline_int_flags=args.inline_int_flags,
            verbose=False
        )


def do_minify(source, filename, minification_args, obfuscation_map=None, module_name_map=None, current_module_name=None, user_modules=None):
    """Minify Python source code with size-based fallback."""
    preserve_globals = []
    if minification_args.preserve_globals:
        for arg in minification_args.preserve_globals:
            names = [name.strip() for name in arg.split(',') if name]
            preserve_globals.extend(names)

    preserve_locals = []
    if minification_args.preserve_locals:
        for arg in minification_args.preserve_locals:
            names = [name.strip() for name in arg.split(',') if name]
            preserve_locals.extend(names)

    if minification_args.remove_annotations is False:
        remove_annotations = RemoveAnnotationsOptions(
            remove_variable_annotations=False,
            remove_return_annotations=False,
            remove_argument_annotations=False,
            remove_class_attribute_annotations=False,
        )
    else:
        remove_annotations = RemoveAnnotationsOptions(
            remove_variable_annotations=minification_args.remove_variable_annotations,
            remove_return_annotations=minification_args.remove_return_annotations,
            remove_argument_annotations=minification_args.remove_argument_annotations,
            remove_class_attribute_annotations=minification_args.remove_class_attribute_annotations,
        )

    defines = {}
    if getattr(minification_args, 'defines', None):
        for d in minification_args.defines:
            if '=' in d:
                name, val = d.split('=', 1)
                defines[name.strip()] = val.strip() not in ('0', 'False', 'false')
            else:
                defines[d.strip()] = True

    minified_result = minify(
        source,
        filename=filename,
        combine_imports=minification_args.combine_imports,
        remove_pass=minification_args.remove_pass,
        remove_annotations=remove_annotations,
        remove_literal_statements=minification_args.remove_literal_statements,
        hoist_literals=minification_args.hoist_literals,
        rename_locals=minification_args.rename_locals,
        preserve_locals=preserve_locals,
        rename_globals=minification_args.rename_globals,
        preserve_globals=preserve_globals,
        remove_object_base=minification_args.remove_object_base,
        convert_posargs_to_args=minification_args.convert_posargs_to_args,
        preserve_shebang=minification_args.preserve_shebang,
        optimize=minification_args.optimize,
        remove_explicit_return_none=minification_args.remove_explicit_return_none,
        remove_builtin_exception_brackets=minification_args.remove_exception_brackets,
        constant_folding=minification_args.constant_folding,
        prefer_single_line=minification_args.prefer_single_line,
        obfuscation_map=obfuscation_map,
        module_name_map=module_name_map,
        current_module_name=current_module_name,
        user_modules=user_modules,
        ignore_all=minification_args.ignore_all,
        threads=minification_args.threads,
        transform_passes=minification_args.transform_passes,
        strict=getattr(minification_args, 'strict_docstrings', True),
        defines=defines,
        remove_type_stmt=getattr(minification_args, 'remove_type_stmt', True),
        simplify_dynamic_attrs=getattr(minification_args, 'simplify_dynamic_attrs', True),
        simplify_fstring=getattr(minification_args, 'simplify_fstring', True),
        simplify_early_exit=getattr(minification_args, 'simplify_early_exit', True),
        simplify_if_stmt=getattr(minification_args, 'simplify_if_stmt', True),
        convert_to_ternary=getattr(minification_args, 'convert_to_ternary', True),
        convert_to_lambda=getattr(minification_args, 'convert_to_lambda', True),
        inline_functions=getattr(minification_args, 'inline_functions', True),
        inline_int_flags=getattr(minification_args, 'inline_int_flags', True),
    )

    minified_bytes = minified_result.encode('utf-8')

    if os.environ.get('PYMINIFY_FORCE_BEST_EFFORT') or os.environ.get('TERSER_FORCE_BEST_EFFORT'):
        return minified_bytes

    if not module_name_map and len(minified_bytes) > len(source):
        raise MinificationNotBeneficialError("Minified output is longer than original")

    return minified_bytes


def _parse_args():
    parser = argparse.ArgumentParser(
        'terser',
        description=__import__("terser").__doc__,
        epilog=main.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'path',
        nargs='+',
        type=str,
        help='The source file or directory to minify. Use "-" to read from stdin. Directories are recursively searched for ".py" files to minify. May be used multiple times',
    )

    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument(
        '--output', '-o',
        action='store',
        help='Path to write minified output. When source is multiple files or a directory, this specifies the output directory',
        dest='output'
    )
    output_options.add_argument(
        '--in-place', '-i',
        action='store_true',
        help='Overwrite existing files. Required when there is more than one source module',
        dest='in_place'
    )

    parser.add_argument(
        '--obfuscation-map', '-m',
        action='store',
        help='Path to write the JSON obfuscation map',
        dest='obfuscation_map'
    )

    # Minification arguments
    minification_options = parser.add_argument_group('minification options', 'Options that affect how the source is minified')
    minification_options.add_argument(
        '--threads',
        type=int,
        default=4,
        help='Number of worker threads to use for parallel tasks',
        dest='threads',
    )
    minification_options.add_argument(
        '--transform-passes',
        type=int,
        default=3,
        help='Number of times the transform stage repeats',
        dest='transform_passes',
    )
    minification_options.add_argument(
        '--no-combine-imports',
        action='store_false',
        help='Disable combining adjacent import statements',
        dest='combine_imports',
    )
    minification_options.add_argument(
        '--no-remove-pass',
        action='store_false',
        default=True,
        help='Disable removing Pass statements',
        dest='remove_pass',
    )
    minification_options.add_argument(
        '--remove-literal-statements',
        action='store_true',
        help='Enable removing statements that are just a literal (including docstrings)',
        dest='remove_literal_statements',
    )
    minification_options.add_argument(
        '--no-hoist-literals',
        action='store_false',
        help='Disable replacing string and bytes literals with variables',
        dest='hoist_literals',
    )
    minification_options.add_argument(
        '--no-rename-locals',
        action='store_false',
        help='Disable shortening of local names',
        dest='rename_locals'
    )
    minification_options.add_argument(
        '--no-tree-shake',
        action='store_true',
        help='Disable tree-shaking (removing unreachable files)',
        dest='no_tree_shake'
    )
    minification_options.add_argument(
        '--preserve-locals',
        type=str,
        action='append',
        help='Comma separated list of local names that will not be shortened',
        dest='preserve_locals',
        metavar='LOCAL_NAMES'
    )
    minification_options.add_argument(
        '--rename-globals',
        action='store_true',
        help='Enable shortening of global names',
        dest='rename_globals'
    )
    minification_options.add_argument(
        '--preserve-globals',
        type=str,
        action='append',
        help='Comma separated list of global names that will not be shortened',
        dest='preserve_globals',
        metavar='GLOBAL_NAMES'
    )
    minification_options.add_argument(
        '--ignore-all',
        action='store_true',
        help='Ignore __all__ protection when renaming globals',
        dest='ignore_all'
    )
    minification_options.add_argument(
        '--no-remove-object-base',
        action='store_false',
        help='Disable removing object from base class list',
        dest='remove_object_base',
    )
    minification_options.add_argument(
        '--no-convert-posargs-to-args',
        action='store_false',
        help='Disable converting positional only arguments to normal arguments',
        dest='convert_posargs_to_args',
    )
    minification_options.add_argument(
        '--no-preserve-shebang',
        action='store_false',
        help='Disable preserving any shebang line from the source',
        dest='preserve_shebang',
    )

    minification_options.add_argument(
        '--no-remove-explicit-return-none',
        action='store_false',
        help='Disable replacing explicit return None with a bare return',
        dest='remove_explicit_return_none',
    )
    minification_options.add_argument(
        '--no-remove-builtin-exception-brackets',
        action='store_false',
        help='Disable removing brackets when raising builtin exceptions with no arguments',
        dest='remove_exception_brackets',
    )
    minification_options.add_argument(
        '--no-constant-folding',
        action='store_false',
        help='Disable evaluating literal expressions',
        dest='constant_folding',
    )
    minification_options.add_argument(
        '--optimize',
        action='store_true',
        help='Enable removing assert statements and __debug__ checks',
        dest='optimize',
    )
    minification_options.add_argument(
        '--define',
        action='append',
        help='Define preprocessor variable (format: NAME, NAME=1, or NAME=0)',
        dest='defines',
        metavar='NAME',
    )
    minification_options.add_argument(
        '--no-strict-docstrings',
        action='store_false',
        help='Disable preserving module-level docstrings',
        dest='strict_docstrings',
    )
    minification_options.add_argument(
        '--no-remove-type-stmt',
        action='store_false',
        help='Disable removing PEP 695 type statements',
        dest='remove_type_stmt',
    )
    minification_options.add_argument(
        '--no-simplify-dynamic-attrs',
        action='store_false',
        help='Disable simplifying dynamic attributes (getattr/setattr)',
        dest='simplify_dynamic_attrs',
    )
    minification_options.add_argument(
        '--no-simplify-fstring',
        action='store_false',
        help='Disable simplifying f-strings',
        dest='simplify_fstring',
    )
    minification_options.add_argument(
        '--no-simplify-early-exit',
        action='store_false',
        help='Disable simplifying early exit else/elif blocks',
        dest='simplify_early_exit',
    )
    minification_options.add_argument(
        '--no-simplify-if-stmt',
        action='store_false',
        help='Disable simplifying single expression if statements',
        dest='simplify_if_stmt',
    )
    minification_options.add_argument(
        '--no-convert-to-ternary',
        action='store_false',
        help='Disable converting if/else/return to ternary expressions',
        dest='convert_to_ternary',
    )
    minification_options.add_argument(
        '--no-convert-to-lambda',
        action='store_false',
        help='Disable converting simple functions to lambda functions',
        dest='convert_to_lambda',
    )
    minification_options.add_argument(
        '--no-inline-functions',
        action='store_false',
        help='Disable inlining single-expression/private functions',
        dest='inline_functions',
    )
    minification_options.add_argument(
        '--no-inline-int-flags',
        action='store_false',
        help='Disable inlining IntFlag enums',
        dest='inline_int_flags',
    )
    minification_options.add_argument(
        '--prefer-single-line',
        action='store_true',
        help='Prefer multiple statements on a single line separated by semicolons, instead of newlines, where there is no difference in output size',
        dest='prefer_single_line',
    )


    annotation_options = parser.add_argument_group('remove annotations options', 'Options that affect how annotations are removed')
    annotation_options.add_argument(
        '--no-remove-annotations',
        action='store_false',
        help='Disable removing all annotations',
        dest='remove_annotations',
    )
    annotation_options.add_argument(
        '--no-remove-variable-annotations',
        action='store_false',
        help='Disable removing variable annotations',
        dest='remove_variable_annotations',
    )
    annotation_options.add_argument(
        '--no-remove-return-annotations',
        action='store_false',
        help='Disable removing function return annotations',
        dest='remove_return_annotations',
    )
    annotation_options.add_argument(
        '--no-remove-argument-annotations',
        action='store_false',
        help='Disable removing function argument annotations',
        dest='remove_argument_annotations',
    )
    annotation_options.add_argument(
        '--remove-class-attribute-annotations',
        action='store_true',
        help='Enable removing class attribute annotations',
        dest='remove_class_attribute_annotations',
    )

    parser.add_argument('--version', '-v', action='version', version=version)

    args = parser.parse_args()

    # Handle some invalid argument combinations
    if '-' in args.path and len(args.path) != 1:
        sys.stderr.write('error: multiple path arguments, reading from stdin not allowed\n')
        sys.exit(1)
    if '-' in args.path and args.in_place:
        sys.stderr.write('error: reading from stdin, --in-place is not valid\n')
        sys.exit(1)
    if len(args.path) > 1 and not args.in_place and not args.output:
        sys.stderr.write('error: multiple path arguments, --in-place or --output required\n')
        sys.exit(1)
    if len(args.path) == 1 and os.path.isdir(args.path[0]) and not args.in_place and not args.output:
        sys.stderr.write('error: path ' + args.path[0] + ' is a directory, --in-place or --output required\n')
        sys.exit(1)

    if args.remove_class_attribute_annotations and not args.remove_annotations:
        sys.stderr.write('error: --remove-class-attribute-annotations would do nothing when used with --no-remove-annotations\n')
        sys.exit(1)

    return args
