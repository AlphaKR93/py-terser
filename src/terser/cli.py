from __future__ import print_function

import argparse
import os
import sys
import json

from terser.api import minify, UnstableMinification
from terser.transforms.remove_annotations_options import RemoveAnnotationsOptions

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


class MinificationNotBeneficialError(Exception):
    """Raised when minification results in larger output than the original."""
    pass


def stdout_write_bytes(data):
    """Write bytes to stdout with proper compatibility."""
    if sys.version_info >= (3, 0):
        sys.stdout.buffer.write(data)
    else:
        sys.stdout.write(data)


if sys.version_info >= (3, 8):
    from importlib import metadata
    try:
        version = metadata.version('py-terser')
    except metadata.PackageNotFoundError:
        version = '0.0.0'
else:
    from pkg_resources import DistributionNotFound, get_distribution
    try:
        version = get_distribution('py-terser').version
    except DistributionNotFound:
        version = '0.0.0'


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

    args = parse_args()

    # 1. Collect all paths to minify
    if len(args.path) == 1 and args.path[0] == '-':
        paths = ['stdin']
    else:
        paths = list(source_modules(args))

    # 2. Build module_name_map if we have files (not stdin)
    module_name_map = {}
    user_modules = set()
    if paths != ['stdin']:
        def get_relative_components(path, search_roots):
            for root in search_roots:
                if os.path.isdir(root):
                    abs_root = os.path.abspath(root)
                    abs_path = os.path.abspath(path)
                    if abs_path.startswith(abs_root):
                        rel = os.path.relpath(abs_path, abs_root)
                        parts = rel.split(os.sep)
                        if parts[-1].endswith(('.py', '.pyw')):
                            parts[-1] = os.path.splitext(parts[-1])[0]
                        return parts
            return None

        # Collect unique components and user module names
        preserved_components = set()
        if args.preserve_globals:
            for arg in args.preserve_globals:
                for name in arg.split(','):
                    name = name.strip()
                    if not name:
                        continue
                    if ':' in name:
                        mod_part, name_part = name.split(':', 1)
                        preserved_components.add(name_part)
                        for p in mod_part.split('.'):
                            preserved_components.add(p)
                    else:
                        preserved_components.add(name)

        import builtins
        builtin_names = set(dir(builtins))
        import terser.ast_compat as ast

        all_components = set()
        for path in paths:
            parts = get_relative_components(path, args.path)
            if parts:
                dotted = '.'.join(parts)
                user_modules.add(dotted)
                for i in range(1, len(parts)):
                    user_modules.add('.'.join(parts[:i]))
                for p in parts:
                    if p != '__init__' and p not in preserved_components:
                        all_components.add(p)

                try:
                    with open(path, 'rb') as f:
                        content = f.read()
                    tree = ast.parse(content, path)
                    for node in tree.body:
                        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                            name = node.name
                            if name not in builtin_names and not (name.startswith('__') and name.endswith('__')) and name not in preserved_components:
                                all_components.add(name)
                        elif isinstance(node, ast.Assign):
                            for target in node.targets:
                                for name_node in ast.walk(target):
                                    if isinstance(name_node, ast.Name) and isinstance(name_node.ctx, ast.Store):
                                        name = name_node.id
                                        if name not in builtin_names and not (name.startswith('__') and name.endswith('__')) and name not in preserved_components:
                                            all_components.add(name)
                        elif isinstance(node, ast.AnnAssign):
                            if isinstance(node.target, ast.Name):
                                name = node.target.id
                                if name not in builtin_names and not (name.startswith('__') and name.endswith('__')) and name not in preserved_components:
                                    all_components.add(name)
                except Exception:
                    pass

        # Generate short names
        import itertools
        def short_name_generator():
            chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
            for length in itertools.count(1):
                for p in itertools.product(chars, repeat=length):
                    yield ''.join(p)

        sorted_components = sorted(list(all_components))
        gen = short_name_generator()
        module_name_map = {comp: next(gen) for comp in sorted_components}

    # 3. Process stdin
    if paths == ['stdin']:
        source = sys.stdin.buffer.read() if sys.version_info >= (3, 0) else sys.stdin.read()
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

        if args.obfuscation_map_file:
            all_mappings = {
                "modules": {},
                "files": {"stdin": obfuscation_map}
            }
            path_to_write = args.obfuscation_map_file
            if os.path.isdir(path_to_write):
                path_to_write = os.path.join(path_to_write, 'obfuscation_map.json')
            with open(path_to_write, 'w', encoding='utf-8') as f:
                json.dump(all_mappings, f, indent=2)

        if args.output:
            with open(args.output, 'wb') as f:
                f.write(minified)
        else:
            stdout_write_bytes(minified)

    # 4. Process multiple files
    else:
        from concurrent.futures import ThreadPoolExecutor
        from terser.transforms.module_obfuscator import ImportedNamesCollector

        # Filter paths to only include reachable files
        reachable_paths = []
        unreachable_paths = []
        if len(paths) <= 1:
            reachable_paths = list(paths)
        else:
            # Collect imports for all files to determine reachability
            file_imports = {}
            for path in paths:
                parts = get_relative_components(path, args.path)
                if parts:
                    dotted_name = '.'.join(parts)
                    try:
                        with open(path, 'rb') as f:
                            content = f.read()
                        tree = ast.parse(content, path)
                        collector = ImportedNamesCollector(dotted_name)
                        collector.visit(tree)
                        imports = set()
                        for abs_mod in collector.imported_modules.values():
                            parts_mod = abs_mod.split('.')
                            for i in range(len(parts_mod), 0, -1):
                                prefix = '.'.join(parts_mod[:i])
                                if prefix in user_modules:
                                    imports.add(prefix)
                                    break
                        file_imports[dotted_name] = imports
                    except Exception:
                        file_imports[dotted_name] = set()

            reachable_modules = set()
            queue = []
            for path in paths:
                parts = get_relative_components(path, args.path)
                if parts:
                    dotted_name = '.'.join(parts)
                    if '_vendor' not in path:
                        reachable_modules.add(dotted_name)
                        queue.append(dotted_name)
                        for i in range(1, len(parts)):
                            reachable_modules.add('.'.join(parts[:i]))

            while queue:
                curr = queue.pop(0)
                for imp in file_imports.get(curr, []):
                    if imp not in reachable_modules:
                        reachable_modules.add(imp)
                        queue.append(imp)
                        parts_imp = imp.split('.')
                        for i in range(1, len(parts_imp)):
                            reachable_modules.add('.'.join(parts_imp[:i]))

            for path in paths:
                parts = get_relative_components(path, args.path)
                if parts:
                    dotted_name = '.'.join(parts)
                    if dotted_name in reachable_modules:
                        reachable_paths.append(path)
                    else:
                        unreachable_paths.append(path)
                else:
                    reachable_paths.append(path)

        def process_path(path):
            with open(path, 'rb') as f:
                source = f.read()
            obfuscation_map = {}
            parts = get_relative_components(path, args.path)
            dotted_name = '.'.join(parts) if parts else None
            try:
                minified = do_minify(source, path, args, obfuscation_map, module_name_map, current_module_name=dotted_name, user_modules=user_modules)
                return path, minified, None, obfuscation_map
            except MinificationNotBeneficialError:
                return path, source, 'not_beneficial', {}
            except Exception as e:
                return path, source, e, {}

        with ThreadPoolExecutor() as executor:
            if HAS_TQDM and len(reachable_paths) > 1:
                results = list(tqdm(executor.map(process_path, reachable_paths), total=len(reachable_paths), desc="Minifying", unit="file"))
            else:
                results = list(executor.map(process_path, reachable_paths))

        # Build fully-qualified module name map: "a.b.c" -> "x.y.z"
        fq_module_map = {}
        for mod_path in sorted(user_modules):
            parts = mod_path.split('.')
            obf_parts = [module_name_map.get(p, p) for p in parts]
            obf_path = '.'.join(obf_parts)
            if obf_path != mod_path:
                fq_module_map[mod_path] = obf_path

        all_mappings = {
            "modules": fq_module_map,
            "files": {}
        }

        # Helper to compute obfuscated new path
        def get_new_path(path, search_roots, module_name_map_dict, output_root=None):
            for root in search_roots:
                if os.path.isdir(root):
                    abs_root = os.path.abspath(root)
                    abs_path = os.path.abspath(path)
                    if abs_path.startswith(abs_root):
                        rel = os.path.relpath(abs_path, abs_root)
                        parts = rel.split(os.sep)
                        new_parts = []
                        for i, p in enumerate(parts):
                            if i == len(parts) - 1:
                                base, ext = os.path.splitext(p)
                                if base != '__init__':
                                    base = module_name_map_dict.get(base, base)
                                new_parts.append(base + ext)
                            else:
                                new_parts.append(module_name_map_dict.get(p, p))
                        dest_root = os.path.abspath(output_root) if output_root else abs_root
                        return os.path.join(dest_root, *new_parts)
            return path

        original_files_to_delete = []

        for path, data, status, obfuscation_map in results:
            parts = get_relative_components(path, args.path)
            file_key = '.'.join(parts) if parts else path
            all_mappings["files"][file_key] = obfuscation_map

            if status is None or status == 'not_beneficial':
                if args.in_place:
                    new_path = get_new_path(path, args.path, module_name_map, output_root=None)
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    with open(new_path, 'wb') as f:
                        f.write(data)
                    sys.stdout.write(path + ' -> ' + new_path + '\n')
                    if os.path.abspath(new_path) != os.path.abspath(path):
                        original_files_to_delete.append(path)
                elif args.output:
                    if len(paths) > 1 or (len(args.path) == 1 and os.path.isdir(args.path[0])):
                        new_path = get_new_path(path, args.path, module_name_map, output_root=args.output)
                    else:
                        new_path = args.output
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    with open(new_path, 'wb') as f:
                        f.write(data)
                    sys.stdout.write(path + ' -> ' + new_path + '\n')
                else:
                    stdout_write_bytes(data)
            else:
                sys.stderr.write('Error minifying {}: {}\n'.format(path, status))
                if args.in_place:
                    new_path = get_new_path(path, args.path, module_name_map, output_root=None)
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    with open(new_path, 'wb') as f:
                        f.write(data)
                    sys.stdout.write(path + ' -> ' + new_path + ' (fallback to original due to error)\n')
                    if os.path.abspath(new_path) != os.path.abspath(path):
                        original_files_to_delete.append(path)
                elif args.output:
                    if len(paths) > 1 or (len(args.path) == 1 and os.path.isdir(args.path[0])):
                        new_path = get_new_path(path, args.path, module_name_map, output_root=args.output)
                    else:
                        new_path = args.output
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    with open(new_path, 'wb') as f:
                        f.write(data)
                    sys.stdout.write(path + ' -> ' + new_path + ' (fallback to original due to error)\n')
                else:
                    stdout_write_bytes(data)

        if args.in_place:
            for path in unreachable_paths:
                original_files_to_delete.append(path)

        # Delete old renamed or unused files
        for old_p in original_files_to_delete:
            try:
                os.remove(old_p)
            except Exception as e:
                sys.stderr.write('Error removing original file {}: {}\n'.format(old_p, e))

        # Clean empty directories
        if args.in_place:
            for root in args.path:
                for dirpath, dirnames, filenames in os.walk(os.path.abspath(root), topdown=False):
                    if not dirnames and not filenames:
                        try:
                            os.rmdir(dirpath)
                        except Exception:
                            pass

        # Write obfuscation map to JSON file
        if args.obfuscation_map_file:
            path_to_write = args.obfuscation_map_file
            if os.path.isdir(path_to_write):
                path_to_write = os.path.join(path_to_write, 'obfuscation_map.json')
            with open(path_to_write, 'w', encoding='utf-8') as f:
                json.dump(all_mappings, f, indent=2)


def parse_args():
    parser = argparse.ArgumentParser(prog='terser', description='Minify Python source code', formatter_class=argparse.RawDescriptionHelpFormatter, epilog=main.__doc__)

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
        dest='obfuscation_map_file'
    )

    parser.add_argument(
        '--prefer-single-line',
        action='store_true',
        help='Prefer multiple statements on a single line separated by semicolons, instead of newlines, where there is no difference in output size',
        dest='prefer_single_line',
    )

    # Minification arguments
    minification_options = parser.add_argument_group('minification options', 'Options that affect how the source is minified')
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
        '--remove-asserts',
        action='store_true',
        help='Enable removing assert statements',
        dest='remove_asserts',
    )
    minification_options.add_argument(
        '--remove-debug',
        action='store_true',
        help='Enable removing conditional statements that test __debug__ is True',
        dest='remove_debug',
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


def source_modules(args):
    def error(os_error):
        raise os_error

    for path_arg in args.path:
        if os.path.isdir(path_arg):
            for root, _dirs, files in os.walk(path_arg, onerror=error, followlinks=True):
                for file in files:
                    if file.endswith(('.py', '.pyw')):
                        yield os.path.join(root, file)
        else:
            yield path_arg


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
        remove_asserts=minification_args.remove_asserts,
        remove_debug=minification_args.remove_debug,
        remove_explicit_return_none=minification_args.remove_explicit_return_none,
        remove_builtin_exception_brackets=minification_args.remove_exception_brackets,
        constant_folding=minification_args.constant_folding,
        prefer_single_line=minification_args.prefer_single_line,
        obfuscation_map=obfuscation_map,
        module_name_map=module_name_map,
        current_module_name=current_module_name,
        user_modules=user_modules,
        ignore_all=minification_args.ignore_all,
    )

    minified_bytes = minified_result.encode('utf-8')

    if os.environ.get('PYMINIFY_FORCE_BEST_EFFORT') or os.environ.get('TERSER_FORCE_BEST_EFFORT'):
        return minified_bytes

    if not module_name_map and len(minified_bytes) > len(source):
        raise MinificationNotBeneficialError("Minified output is longer than original")

    return minified_bytes
