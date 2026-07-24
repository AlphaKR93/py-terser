from __future__ import print_function

import argparse
import asyncio
import os
import sys

from alpha93.argparse import arguments_from_model

from terser import minify, minify_project
from .._pipeline.mangler.util import preserved_names
from ._argv import TerserArguments, TerserParsedArguments, parse_preserve
from ._tqdm import TqdmReporter


class MinificationNotBeneficialError(Exception):
    """Raised when minification results in larger output than the original."""
    pass

def main():
    """
    examples:
      # Minifying stdin to stdout
      pyminify -

      # Minifying a file to stdout
      pyminify example.py

      # Minifying a file and writing to a different file
      pyminify example.py --output example.min.py

      # Minifying a file in place
      pyminify example.py --in-place

      # Minifying all *.py files in a directory
      pyminify src/ --in-place

      # Minifying a directory to a separate output directory
      pyminify src/ --output build/

      # Minifying multiple paths in place
      pyminify file1.py file2.py src/ --in-place
    """

    args = parse_args()

    # Directories and multiple paths are minified as a project (whole-project name
    # resolution/linking), so route them separately.
    if is_project_mode(args):
        asyncio.run(do_minify_project(args))
        return

    # minify stdin
    if len(args.path) == 1 and next(iter(args.path)) == '-':
        source = sys.stdin.buffer.read()
        try:
            minified = do_minify(source, "<stdin>", args)
        except MinificationNotBeneficialError:
            # Use original source when minification isn't beneficial
            if args.output_options.output:
                with open(args.output_options.output, 'wb') as f:
                    f.write(source)
            else:
                # Write original source to stdout
                sys.stdout.buffer.write(source)
            return

        if args.output_options.output:
            with open(args.output_options.output, 'wb') as f:
                f.write(minified)
        else:
            sys.stdout.buffer.write(minified)
        return

    # parse_args() only allows a single, non-directory path to reach this point
    path = next(iter(args.path))

    with open(path, 'rb') as f:
        source = f.read()

    try:
        minified = do_minify(source, path, args)
    except MinificationNotBeneficialError:
        # Use original source when minification isn't beneficial
        if args.output_options.output:
            with open(args.output_options.output, 'wb') as f:
                f.write(source)
        else:
            stdout_write_bytes(source)
        return

    if args.output_options.output:
        with open(args.output_options.output, 'wb') as f:
            f.write(minified)
    else:
        stdout_write_bytes(minified)


def is_project_mode(args: TerserParsedArguments) -> bool:
    """Whether whole-project linking (multiple modules, cross-file renames) is needed."""

    if args.output_options.in_place:
        return True
    if len(args.path) > 1:
        return True

    path = next(iter(args.path))
    return path != '-' and os.path.isdir(path)


def parse_args() -> TerserParsedArguments:
    python_minifier = __import__("terser")
    parser = argparse.ArgumentParser("terser", None, python_minifier.__doc__, main.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    #parser.add_argument("--help", "-h", action="help")
    parser.add_argument("-v", "--version", action="version", version=python_minifier.version)

    parser.add_argument(
        'path',
        nargs='+',
        type=str,
        help='The source file or directory to minify. Use "-" to read from stdin. Directories are recursively searched for ".py" files to minify. May be used multiple times',
    )

    arguments_from_model(parser, TerserArguments)
    args = TerserParsedArguments.from_argparse(parser.parse_args())

    # Handle some invalid argument combinations
    if '-' in args.path and len(args.path) != 1:
        sys.stderr.write('error: multiple path arguments, reading from stdin not allowed\n')
        sys.exit(1)
    if '-' in args.path and args.output_options.in_place:
        sys.stderr.write('error: reading from stdin, --in-place is not valid\n')
        sys.exit(1)
    if len(args.path) > 1 and not (args.output_options.in_place or args.output_options.output):
        sys.stderr.write('error: multiple path arguments, --in-place or --output required\n')
        sys.exit(1)
    if len(args.path) == 1 and os.path.isdir(p := next(iter(args.path))) and not (args.output_options.in_place or args.output_options.output):
        sys.stderr.write('error: path ' + p + ' is a directory, --in-place or --output required\n')
        sys.exit(1)
    if not is_project_mode(args) and (args.mangling_options.rename_globals or args.mangling_options.preserve_globals):
        sys.stderr.write('error: --rename-globals/--preserve-globals require a directory, multiple paths, or --in-place, since global renaming needs whole-project linking\n')
        sys.exit(1)
    if not is_project_mode(args) and (args.entry or args.mangling_options.rename_modules or args.mangling_options.preserve_modules):
        sys.stderr.write('error: --entry/--rename-modules/--preserve-modules require a directory, multiple paths, or --in-place, since these need whole-project linking\n')
        sys.exit(1)
    if args.mangling_options.rename_modules and not args.output_options.output:
        sys.stderr.write('error: --rename-modules requires --output, since renamed files can\'t be written back in-place\n')
        sys.exit(1)

    return args


def do_minify(source: bytes, path: str, args: TerserParsedArguments) -> bytes:
    """Minify Python source code with size-based fallback.

    :param bytes source: Source code as bytes (from file 'rb' or stdin.buffer)
    :param str path: Filename for error reporting
    :param TerserParsedArguments args: CLI arguments for minification options
    :returns: Minified source code as UTF-8 bytes
    :raises MinificationNotBeneficialError: When minified output is larger than original
    """

    preserve_locals = sorted(preserved_names(path, parse_preserve(args.mangling_options.preserve_locals)))

    minified_result = minify(
        source.decode('utf-8'),
        args.transform_options,
        path,
        preserve_shebang=args.preserve_shebang,
        prefer_single_line=args.prefer_single_line,
        hoist_literals=args.mangling_options.hoist_literals,
        rename_locals=args.mangling_options.rename_locals,
        preserve_locals=preserve_locals,
    )

    # Encode minified result to bytes for comparison and output
    minified_bytes = minified_result.encode('utf-8')

    # Check if environment variable forces minified output
    if os.environ.get('PYMINIFY_FORCE_BEST_EFFORT'):
        return minified_bytes

    # Compare byte lengths for accurate size comparison
    if len(minified_bytes) > len(source):
        raise MinificationNotBeneficialError("Minified output is longer than original")

    return minified_bytes


async def do_minify_project(args: TerserParsedArguments):
    """Minify a directory/multi-file project, using whole-project linking.

    Writes back to each module's own file (--in-place), or under the --output
    directory (mirroring each module's path relative to its source root).
    """

    await minify_project(
        args.path,
        args.transform_options,
        args.output_options.output,
        TqdmReporter(),
        hoist_literals=args.mangling_options.hoist_literals,
        rename_locals=args.mangling_options.rename_locals,
        preserve_locals=parse_preserve(args.mangling_options.preserve_locals),
        rename_globals=args.mangling_options.rename_globals,
        preserve_globals=parse_preserve(args.mangling_options.preserve_globals),
        rename_modules=args.mangling_options.rename_modules,
        preserve_modules=args.mangling_options.preserve_modules,
        entry=args.entry,
    )


def stdout_write_bytes(data: bytes):
    sys.stdout.buffer.write(data)
