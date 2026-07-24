from concurrent.futures import ThreadPoolExecutor

from ._ast import ast, tree as _ast
from .config import TerserConfig
from .parse import preprocess, travel
from ._utils.progress import ProgressReporter

if __debug__ and __import__("typing").TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


SOURCE_EXTENSIONS = (".py", ".pyw",)


async def async_minify_project(
    sources: Iterable[str],
    config: TerserConfig,
    reporter: ProgressReporter,
    output: str | None = None,
    mangling_map_file: str | None = None,
    preserve_locals: Iterable[str] | None = None,
    preserve_globals: Iterable[str] | None = None,
    defines: Mapping[str, bool] | None = None,
    strict: bool = False,
    verbose: bool = False
):
    """
    Minify a Python project/directory.
    """
    from anyio import Path

    import os
    import sys
    import json
    from python_minifier.transforms.module_obfuscator import ImportedNamesCollector

    paths = await travel(*sources, strict=strict, follow_symlinks=output is None)
    del sources

    with reporter.step("Parsing nodes") as step:
        compile_args = {
            "type_comments": False,
            "feature_version": config.target_version,
            "optimize":
                2 if (config.optimize
                      and config.remove_docstrings
                      and not config.preserve_module_docstrings)
                else None
        }

        async def process(args: tuple[Path, Path], /):
            path, root = args
            if not (await path.exists()):
                raise FileNotFoundError(path)
            elif not (await path.is_dir()):
                raise IsADirectoryError(path)

            source, shebang = preprocess(await path.read_text("utf-8"), defines, strict)
            node = _ast.parse(source, str(fp), **compile_args)

        with ThreadPoolExecutor(max_workers=config.threads) as executor:
            executor.map(process, paths)

    # get_relative_components helper
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
            elif os.path.isfile(root):
                abs_root = os.path.abspath(root)
                abs_path = os.path.abspath(path)
                if abs_path == abs_root:
                    basename = os.path.basename(path)
                    if basename.endswith(('.py', '.pyw')):
                        basename = os.path.splitext(basename)[0]
                    return [basename]
        return None

    # module_name_map & user_modules generation
    user_modules = set()
    preserved_components = set()

    if preserve_globals:
        for val in preserve_globals:
            for name in val.split(','):
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

    # Collect cross-module names to preserve
    cross_module_names = set()
    for path in paths:
        try:
            with open(path, 'rb') as f:
                content = f.read()
            tree = ast.parse(content, path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name != '*':
                            cross_module_names.add(alias.name)
                elif isinstance(node, ast.Attribute):
                    cross_module_names.add(node.attr)
                elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for el in node.value.elts:
                                val = getattr(el, 'value', getattr(el, 's', None))
                                if isinstance(val, str):
                                    cross_module_names.add(val)
        except Exception:
            pass
    preserved_components.update(cross_module_names)

    all_components = set()
    for path in paths:
        parts = get_relative_components(path, search_paths)
        if parts:
            dotted = '.'.join(parts)
            user_modules.add(dotted)
            for i in range(1, len(parts)):
                user_modules.add('.'.join(parts[:i]))
            for p in parts:
                if p != '__init__' and p not in preserved_components:
                    all_components.add(p)

    import itertools
    import keyword
    def short_name_generator():
        chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        for length in itertools.count(1):
            for p in itertools.product(chars, repeat=length):
                name = ''.join(p)
                if not keyword.iskeyword(name):
                    yield name

    sorted_components = sorted(list(all_components))
    gen = short_name_generator()
    if len(paths) > 1 or (len(search_paths) == 1 and os.path.isdir(search_paths[0])):
        module_name_map = {comp: next(gen) for comp in sorted_components}
    else:
        module_name_map = {}

    parsed_preserve_globals = []
    if preserve_globals:
        for val in preserve_globals:
            names = [name.strip() for name in val.split(',') if name]
            parsed_preserve_globals.extend(names)
    if preserved_components:
        parsed_preserve_globals.append(','.join(list(preserved_components)))

    # Filter reachable paths (tree shaking)
    reachable_paths = []
    unreachable_paths = []
    if no_tree_shake or len(paths) <= 1:
        reachable_paths = list(paths)
    else:
        file_imports = {}
        for path in paths:
            parts = get_relative_components(path, search_paths)
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
            parts = get_relative_components(path, search_paths)
            if parts:
                dotted_name = '.'.join(parts)
                if '_vendor' not in path:
                    reachable_modules.add(dotted_name)
                    queue.append(dotted_name)
                    for i in range(1, len(parts)):
                        reachable_modules.add('.'.join(parts[:i]))

        while queue:
            curr = queue.pop(0)
            init_name = curr + '.__init__'
            if init_name in file_imports:
                if init_name not in reachable_modules:
                    reachable_modules.add(init_name)
                    queue.append(init_name)

            for imp in file_imports.get(curr, []):
                if imp not in reachable_modules:
                    reachable_modules.add(imp)
                    queue.append(imp)
                    parts_imp = imp.split('.')
                    for i in range(1, len(parts_imp)):
                        parent = '.'.join(parts_imp[:i])
                        if parent not in reachable_modules:
                            reachable_modules.add(parent)
                            queue.append(parent)

        for path in paths:
            parts = get_relative_components(path, search_paths)
            if parts:
                dotted_name = '.'.join(parts)
                if dotted_name in reachable_modules:
                    reachable_paths.append(path)
                else:
                    unreachable_paths.append(path)
            else:
                reachable_paths.append(path)

    # Configure and run Pipeline
    parsed_defines = {}
    if defines:
        for d in defines:
            if '=' in d:
                name, val = d.split('=', 1)
                parsed_defines[name.strip()] = val.strip() not in ('0', 'False', 'false')
            else:
                parsed_defines[d.strip()] = True

    # Map remove_annotations options
    remove_ann = True
    remove_var_ann = True
    remove_ret_ann = True
    remove_arg_ann = True
    remove_cls_ann = False
    if isinstance(remove_annotations, bool):
        remove_ann = remove_annotations
        remove_var_ann = remove_annotations
        remove_ret_ann = remove_annotations
        remove_arg_ann = remove_annotations
        remove_cls_ann = remove_annotations
    elif isinstance(remove_annotations, RemoveAnnotationsOptions):
        remove_ann = (
                remove_annotations.remove_variable_annotations or
                remove_annotations.remove_return_annotations or
                remove_annotations.remove_argument_annotations or
                remove_annotations.remove_class_attribute_annotations
        )
        remove_var_ann = remove_annotations.remove_variable_annotations
        remove_ret_ann = remove_annotations.remove_return_annotations
        remove_arg_ann = remove_annotations.remove_argument_annotations
        remove_cls_ann = remove_annotations.remove_class_attribute_annotations

    obfuscation_map_dict = {}
    config = TerserConfig(
        threads=threads,
        transform_passes=transform_passes,
        fold_constants=constant_folding,
        optimize=optimize,
        defines=parsed_defines,
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
        preserve_globals=parsed_preserve_globals,
        ignore_all=ignore_all,
        prefer_single_line=prefer_single_line,
        preserve_shebang=preserve_shebang,
        obfuscation_map=obfuscation_map_dict,
        rename_map=rename_map,
        module_name_map=module_name_map,
        user_modules=user_modules,
        no_tree_shake=no_tree_shake
    )

    pipeline = Pipeline(config)
    results = pipeline.run(reachable_paths)

    # Fully-qualified module name map
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

    # get_new_path helper
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

    # Map file outputs and populate mappings
    for res in results:
        parts = get_relative_components(res.path, search_paths)
        file_key = '.'.join(parts) if parts else str(res.path)
        all_mappings["files"][file_key] = obfuscation_map_dict

        # Determine code bytes to write, falling back if not beneficial
        code_bytes = res.code if isinstance(res.code, bytes) else res.code.encode('utf-8')
        if not module_name_map and not os.environ.get('PYMINIFY_FORCE_BEST_EFFORT') and not os.environ.get('TERSER_FORCE_BEST_EFFORT'):
            try:
                with open(res.path, 'rb') as f:
                    orig = f.read()
                if len(code_bytes) > len(orig):
                    code_bytes = orig
            except Exception:
                pass

        # Output resolution and writing
        if in_place:
            new_path = get_new_path(res.path, search_paths, module_name_map, output_root=None)
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            with open(new_path, 'wb') as f:
                f.write(code_bytes)
            if verbose:
                sys.stdout.write(str(res.path) + ' -> ' + new_path + '\n')
            if os.path.abspath(new_path) != os.path.abspath(res.path):
                original_files_to_delete.append(res.path)
        elif output:
            if len(search_paths) > 1 or (len(search_paths) == 1 and os.path.isdir(search_paths[0])):
                new_path = get_new_path(res.path, search_paths, module_name_map, output_root=output)
            else:
                new_path = output
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            with open(new_path, 'wb') as f:
                f.write(code_bytes)
            if verbose:
                sys.stdout.write(str(res.path) + ' -> ' + new_path + '\n')
        else:
            sys.stdout.buffer.write(code_bytes)

    if in_place:
        for path in unreachable_paths:
            original_files_to_delete.append(path)

    # Delete original source files that were renamed/unused
    for old_p in original_files_to_delete:
        try:
            os.remove(old_p)
        except Exception as e:
            sys.stderr.write('Error removing original file {}: {}\n'.format(old_p, e))

    # Clean empty directories
    if in_place:
        for root in search_paths:
            if os.path.isdir(root):
                for dirpath, dirnames, filenames in os.walk(os.path.abspath(root), topdown=False):
                    if not dirnames and not filenames:
                        try:
                            os.rmdir(dirpath)
                        except Exception:
                            pass

    # Write the JSON obfuscation map
    if obfuscation_map_file:
        path_to_write = obfuscation_map_file
        if os.path.isdir(path_to_write):
            path_to_write = os.path.join(path_to_write, 'obfuscation_map.json')
        with open(path_to_write, 'w', encoding='utf-8') as f:
            json.dump(all_mappings, f, indent=2)

    return results
