from __future__ import print_function

import argparse
import os
import sys

from alpha93.argparse import arguments_from_model

from terser import minify
from ._argv import TerserArguments, TerserParsedArguments


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

      # Minifying multiple paths in place
      pyminify file1.py file2.py src/ --in-place
    """

    args = parse_args()

    # minify stdin
    if len(args.path) == 1 and next(iter(args.path)) == '-':
        source = sys.stdin.buffer.read()
        try:
            minified = do_minify(source, "<stdin>", args)
        except MinificationNotBeneficialError:
            # Use original source when minification isn't beneficial
            if args.output:
                with open(args.output, 'wb') as f:
                    f.write(source)
            else:
                # Write original source to stdout
                sys.stdout.buffer.write(source)
            return

        if args.output:
            with open(args.output, 'wb') as f:
                f.write(minified)
        else:
            sys.stdout.buffer.write(minified)
        return

    for path in source_modules(args):
        if args.output or args.in_place:
            sys.stdout.write(path + '\n')

        with open(path, 'rb') as f:
            source = f.read()

        try:
            minified = do_minify(source, path, args)
        except MinificationNotBeneficialError:
            # Use original source when minification isn't beneficial
            if args.in_place:
                # File is already the original, no need to write
                pass
            elif args.output:
                # Write original source to output
                with open(args.output, 'wb') as f:
                    f.write(source)
            else:
                # Write original source to stdout
                stdout_write_bytes(source)
            continue

        if args.in_place:
            with open(path, 'wb') as f:
                f.write(minified)
        elif args.output:
            with open(args.output, 'wb') as f:
                f.write(minified)
        else:
            stdout_write_bytes(minified)


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
    if len(args.path) > 1 and not args.output_options.in_place:
        sys.stderr.write('error: multiple path arguments, --in-place required\n')
        sys.exit(1)
    if len(args.path) == 1 and os.path.isdir(p := next(iter(args.path))) and not args.output_options.in_place:
        sys.stderr.write('error: path ' + p + ' is a directory, --in-place required\n')
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


def do_minify(source: bytes, path: str, args: TerserParsedArguments) -> bytes:
    """Minify Python source code with size-based fallback.

    :param bytes source: Source code as bytes (from file 'rb' or stdin.buffer)
    :param str path: Filename for error reporting
    :param argparse.Namespace args: CLI arguments for minification options
    :returns: Minified source code as UTF-8 bytes
    :raises MinificationNotBeneficialError: When minified output is larger than original
    """

    # TODO: Migrate into Pydantic models
    preserve_globals = []
    if args.preserve_globals:
        for arg in args.preserve_globals:
            names = [name.strip() for name in arg.split(',') if name]
            preserve_globals.extend(names)
    preserve_locals = []
    if args.preserve_locals:
        for arg in args.preserve_locals:
            names = [name.strip() for name in arg.split(',') if name]
            preserve_locals.extend(names)

    minified_result = minify(
        source,
        args.transform_options,
        path=path,
        hoist_literals=args.hoist_literals,
        rename_locals=args.rename_locals,
        preserve_locals=preserve_locals,
        rename_globals=args.rename_globals,
        preserve_globals=preserve_globals,
        preserve_shebang=args.preserve_shebang,
        prefer_single_line=args.prefer_single_line,
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
