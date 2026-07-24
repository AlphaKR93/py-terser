from __future__ import print_function

import argparse
import os

from .config import TerserConfig
from .transforms.remove_annotations_options import RemoveAnnotationsOptions

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

if __debug__ and __import__("typing").TYPE_CHECKING:
    from collections.abc import Mapping
    from dataclasses import Field
    from typing import Any

version: str = __import__("importlib").metadata.version('py-python_minifier')  # ty: ignore[possibly-missing-submodule]


class MinificationNotBeneficialError(Exception):
    """Raised when minification results in larger output than the original."""


def main():
    """
    examples:
        # Minifying stdin to stdout
        python_minifier -

        # Minifying a file to stdout
        python_minifier example.py

        # Minifying a file and writing to a different file
        python_minifier example.py --output example.min.py

        # Minifying a file in place
        python_minifier example.py --in-place

        # Minifying all *.py files in a directory
        python_minifier src/ --in-place

        # Minifying multiple paths in place
        python_minifier file1.py file2.py src/ --in-place
    """
    argv, config = __build_from_argv()

    if len(argv.path) == 1 and argv.path[0] == "--":
        __stdin(argv, config)
        return

    from python_minifier import minify_project
    minify_project(
        *argv.path,
        config=config,
        output=None if argv.in_place else argv.output,
        obfuscation_map=argv.mapping,
        verbose=argv.verbose
    )


def __stdin(argv: argparse.Namespace, config: TerserConfig):
    from sys import stdin, stdout

    source = stdin.buffer.read()
    obfuscation_map = {}

    def output(data: bytes):
        if argv.output:
            with open(argv.output, 'wb') as f:
                f.write(data)
        else:
            stdout.buffer.write(data)


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

    defines = {}
    if getattr(minification_args, 'defines', None):
        for d in minification_args.defines:
            if '=' in d:
                name, val = d.split('=', 1)
                defines[name.strip()] = val.strip() not in ('0', 'False', 'false')
            else:
                defines[d.strip()] = True

    from .terser import minify
    minified = minify(
        source,
        config,
        filename="<stdin>",
        preserve_locals=preserve_locals,
        preserve_globals=preserve_globals,
        obfuscation_map=obfuscation_map,
        module_name_map=module_name_map,
        current_module_name=current_module_name,
        user_modules=user_modules,
        defines=defines,
    ).encode("utf-8")

    if not module_name_map and len(minified) > len(source):

    mapping: str = argv.mapping
    if os.path.isdir(mapping):
        mapping = os.path.join(mapping, "mapping.json")

    with open(mapping, 'wb', encoding='utf-8') as f:
        from json import dump

        dump({"names": {"<stdin>": obfuscation_map}}, f)

    output(minified)


def __build_from_argv() -> tuple[argparse.Namespace, TerserConfig]:
    parser = argparse.ArgumentParser(
        "python_minifier",
        description=__import__("python_minifier").__doc__,
        epilog=main.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--version", '-v', action='version', version=version)

    parser.add_argument(
        "path",
        help="The source file or directory to minify. Use `--` to read from stdin. Directories are recursively searched for `.py` files to minify. May be used multiple times",
        type=str,
        nargs='+',
    )
    parser.add_argument(
        '--preserve-shebang', "-S",
        action='store_true',
        help='Disable preserving any shebang line from the source',
        dest='preserve_shebang',
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        dest="verbose",
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
    del output_options

    parser.add_argument(
        '--mapping', '-m',
        action='store',
        help='Path to write the JSON obfuscation map',
        dest='mapping',
        default="./mapping.json"
    )

    # <editor-fold defaultstate="collapsed" desc="arguments">
    @lambda _: _()
    def fields():
        from dataclasses import fields
        from .config import TerserConfig

        attrs = {}
        for field in fields(TerserConfig):
            attrs[field.name] = field
        return attrs
    fields: Mapping[str, Field[Any]]

    arg_field = set()
    def from_attrs(group: argparse._ActionsContainer, name: str, *flags: str, **kwargs):
        arg_field.add(name)
        field: Field[Any] = fields[name]
        kwargs.setdefault("dest", name),
        kwargs.setdefault("type", field.type),
        kwargs.setdefault("help", field.metadata["doc"]),
        kwargs.setdefault("default", field.default),

        action: str | None = None
        if field.type is bool:
            if field.default is not None and not field.default:
                name = "no_" + name
            action = "store_false" if field.default else "store_true"
        kwargs["action"] = kwargs.get("action", action)
        del action

        group.add_argument(f"--{name.replace('_', '-')}", *flags, **kwargs)

    from_attrs(parser, "tree_shaking")
    from_attrs(parser, "prefer_oneline")

    # Minification arguments
    minification = parser.add_argument_group('minification options', 'Options that affect how the source is minified')
    from_attrs(minification, "passes", "-p")
    from_attrs(minification, "optimize", "-O")
    from_attrs(minification, "hoist_literals")
    from_attrs(minification, "cleanup_imports")
    from_attrs(minification, "remove_literal_statements")
    from_attrs(minification, "remove_docstrings")
    from_attrs(minification, "preserve_module_docstrings")
    from_attrs(minification, "remove_explicit_inherits")
    from_attrs(minification, "remove_explicit_return_none")
    from_attrs(minification, "remove_trailing_returns")
    from_attrs(minification, "remove_pass")
    from_attrs(minification, "remove_exc_brackets")
    from_attrs(minification, "remove_type_statement")
    from_attrs(minification, "remove_posargs")
    from_attrs(minification, "simplify_fstring")
    from_attrs(minification, "simplify_early_exit")
    from_attrs(minification, "simplify_if_statement")
    from_attrs(minification, "simplify_functions")

    advanced = minification.add_argument_group("advanced options", "")
    advanced.add_argument(
        "--experimental-fold-constants",
        help="Evaluate constant literal expressions",
        dest="fold_constants",
        type=bool,
        action="store_true",
    )
    advanced.add_argument(
        "--experimental-inline-int-flags",
        help="Inline IntFlag when available",
        dest="inline_int_flags",
        type=bool,
        action="store_true",
    )
    advanced.add_argument(
        "--experimental-simplify-dyn-attrs",
        help="Simplify dynamic attributes (getattr/setattr)",
        dest="simplify_dynattrs",
        type=bool,
        action="store_false",
    )
    del advanced

    annotations = parser.add_argument_group('remove annotations options', 'Options that affect how annotations are removed')
    annotations.add_argument(
        '--no-remove-annotations',
        action='store_false',
        help='Disable removing all annotations',
        dest='remove_annotations',
    )
    annotations.add_argument(
        '--no-remove-variable-annotations',
        action='store_false',
        help='Disable removing variable annotations',
        dest='remove_variable_annotations',
    )
    annotations.add_argument(
        '--no-remove-return-annotations',
        action='store_false',
        help='Disable removing function return annotations',
        dest='remove_return_annotations',
    )
    annotations.add_argument(
        '--no-remove-argument-annotations',
        action='store_false',
        help='Disable removing function argument annotations',
        dest='remove_argument_annotations',
    )
    annotations.add_argument(
        '--remove-class-attribute-annotations',
        action='store_true',
        help='Enable removing class attribute annotations',
        dest='remove_class_attribute_annotations',
    )
    del annotations

    name_mangling = minification.add_argument_group("name mangling options", "")
    from_attrs(name_mangling, "rename_locals")
    name_mangling.add_argument(
        "--preserve-locals", "-L",
        help=fields["preserve_locals"].metadata["doc"],
        type=str,
        dest="preserve_locals",
        action="append",
        metavar="LOCAL_NAMES",
    )
    from_attrs(name_mangling, "rename_globals")
    name_mangling.add_argument(
        "--preserve-globals", "-L",
        help=fields["preserve_globals"].metadata["doc"],
        type=str,
        dest="preserve_globals",
        action="append",
        metavar="GLOBALS_NAMES",
    )
    from_attrs(name_mangling, "--ignore-all")
    del name_mangling
    del minification

    from_attrs(parser, "threads")
    parser.add_argument(
        "--define", "-D",
        help=fields["define"].metadata["doc"],
        dest="defines",
        action="append",
        metavar="NAME",
    )
    # </editor-fold>

    args = parser.parse_args()

    # Handle some invalid argument combinations
    import sys

    if len(args.path) > 1:
        if "--" in args.path:
            print("error: multiple path arguments, reading from stdin not allowed", file=sys.stderr)
            sys.exit(1)
        if not args.in_place and not args.output:
            print("error: multiple path arguments, --in-place or --output required", file=sys.stderr)
            sys.exit(1)
    elif args.path[0] == "--":
        if args.in_place:
            print("error: reading from stdin, --in-place is not valid", file=sys.stderr)
            sys.exit(1)
    else:
        if os.path.isdir(args.path[0]) and not args.in_place and not args.output:
            print(f"error: path {args.path[0]} is a directory, --in-place or --output required", file=sys.stderr)
            sys.exit(1)

    config = TerserConfig(
        remove_annotations=RemoveAnnotationsOptions(
            remove_variable_annotations=args.remove_variable_annotations,
            remove_return_annotations=args.remove_return_annotations,
            remove_argument_annotations=args.remove_argument_annotations,
            remove_class_attribute_annotations=args.remove_class_attribute_annotations
        ),
    )
    for arg in arg_field:
        setattr(config, arg, getattr(args, arg, None))

    return args, config
