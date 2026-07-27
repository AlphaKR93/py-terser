from typing import TYPE_CHECKING, Annotated

from alpha93.commons.pydantic import dataclasses
from pydantic import BaseModel, ConfigDict, Field

from terser.config import TransformConfig, RemoveAnnotationOptions, RemoveDocstringOptions
from ._argparse import MutuallyExclusive

if TYPE_CHECKING:
    from argparse import Namespace


_config = ConfigDict(use_attribute_docstrings=True)
PydanticTransformOptions = dataclasses.to_model(TransformConfig)


def parse_preserve(args: set[str]) -> dict[str, list[str]]:
    """
    Parse `--preserve-locals`/`--preserve-globals` values into a glob-pattern -> names map.

    Each argument is either "name[,name...]" (applies to every module, pattern "*") or
    "pattern:name[,name...]" (applies only to modules whose dotted path, or filename in
    single-file mode, matches the glob pattern), e.g. "foo.bar:baz,qux".
    """

    result: dict[str, list[str]] = {}
    for arg in args:
        pattern, sep, names = arg.partition(':')
        if not sep:
            pattern, names = '*', pattern
        pattern = pattern.strip() or '*'

        for name in names.split(','):
            name = name.strip()
            if name:
                result.setdefault(pattern, []).append(name)

    return result


class OutputOptions(BaseModel):
    model_config = _config

    output: str | None = None
    """Path to write minified output. Defaults to stdout."""

    in_place: bool = False
    """Overwrite existing files."""


class ManglingOptions(BaseModel):
    model_config = _config

    hoist_literals: bool = True
    """Replace frequently used constant literals with variables that have shorter name."""

    rename_locals: bool = True
    """Mangle local (including nonlocal) names"""

    preserve_locals: Annotated[set[str], Field(default_factory=set)]
    """Comma-separated list of local names that will not be mangled. Prefix with a
    glob pattern and ':' to scope to matching modules, e.g. 'foo.bar:baz,qux'"""

    rename_globals: bool = False
    """Mangle global names (requires --in-place, since this needs whole-project linking)"""

    preserve_globals: Annotated[set[str], Field(default_factory=set)]
    """Comma-separated list of global names that will not be mangled. Prefix with a
    glob pattern and ':' to scope to matching modules, e.g. 'foo.bar:baz,qux'"""


class TerserArguments(BaseModel):
    model_config = _config

    output_options: MutuallyExclusive[OutputOptions]

    preserve_shebang: bool = True
    """Preserve any shebang line from the source code."""

    prefer_single_line: bool = False
    """
    Prefer multiple statements on a single line separated by semicolons instead of newlines,
    even when there is no difference in output size.
    """

    transform_options: TransformConfig
    """Options that affect how the source is minified"""

    mangling_options: ManglingOptions

    workers: int | None = None
    """Number of worker threads to process modules with in project mode. Defaults to the
    interpreter's default thread pool sizing."""

# TODO: Cleanup this shit
class TerserParsedArguments(TerserArguments):
    path: set[str]

    @classmethod
    def from_argparse(cls, namespace: Namespace, /) -> TerserParsedArguments:
        output_options = OutputOptions(
            output=None if namespace.in_place else namespace.output,
            in_place=namespace.in_place,
        )

        remove_annotations = RemoveAnnotationOptions(
            remove_variable_annotations=namespace.remove_variable_annotations,
            remove_return_annotations=namespace.remove_return_annotations,
            remove_argument_annotations=namespace.remove_argument_annotations,
            remove_attribute_annotations=namespace.remove_attribute_annotations,
        )
        remove_docstrings = RemoveDocstringOptions(
            also_modules=namespace.also_modules,
        )
        transform_options = TransformConfig(
            passes=namespace.passes,
            optimize=namespace.optimize,
            hint_modules=namespace.hint_modules,
            # `--target-version` accumulates via the generic list-flag machinery, which
            # defaults to `[]` - map that back to `None` (folding disabled) since an empty
            # tuple isn't a meaningful version to fold `sys.version_info` comparisons against.
            target_version=tuple(namespace.target_version) if namespace.target_version else None,
            contracts=namespace.contracts,
            apply_contracts=namespace.apply_contracts,
            remove_literal_statements=namespace.remove_literal_statements,
            combine_imports=namespace.combine_imports,
            remove_annotations=remove_annotations if namespace.remove_annotations else False,
            remove_explicit_base=namespace.remove_explicit_base,
            remove_explicit_return_none=namespace.remove_explicit_return_none,
            fold_constants=namespace.fold_constants,
            remove_debug=namespace.remove_debug,
            remove_asserts=namespace.remove_asserts,
            convert_pass=namespace.convert_pass,
            unfold_iife_lambdas=namespace.unfold_iife_lambdas,
            remove_type_statements=namespace.remove_type_statements,
            convert_early_exits=namespace.convert_early_exits,
            convert_to_inline=namespace.convert_to_inline,
            convert_to_lambda=namespace.convert_to_lambda,
            remove_dummy_assignments=namespace.remove_dummy_assignments,
            remove_docstrings=remove_docstrings if namespace.remove_docstrings else False,
            respect_all=namespace.respect_all,
            cleanup_local_imports=namespace.cleanup_local_imports,
            remove_typing_decorators=namespace.remove_typing_decorators,
            remove_overloads=namespace.remove_overloads,
            remove_generics=namespace.remove_generics,
            remove_typing_classes=namespace.remove_typing_classes,
            convert_typing_constructors=namespace.convert_typing_constructors,
            convert_typing_extensions=namespace.convert_typing_extensions,
            convert_dynamic_attribute_access=namespace.convert_dynamic_attribute_access,
            remove_empty_exc_brackets=namespace.remove_empty_exc_brackets,
            convert_posargs=namespace.convert_posargs,
            remove_dunder_all=namespace.remove_dunder_all,
            remove_dunder_all_modules=namespace.remove_dunder_all_modules,
        )

        mangling_options = ManglingOptions(
            hoist_literals=namespace.hoist_literals,
            rename_locals=namespace.rename_locals,
            preserve_locals=namespace.preserve_locals,
            rename_globals=namespace.rename_globals,
            preserve_globals=namespace.preserve_globals,
        )

        return cls(
            path=namespace.path,
            output_options=output_options,
            preserve_shebang=namespace.preserve_shebang,
            prefer_single_line=namespace.prefer_single_line,
            transform_options=transform_options,
            mangling_options=mangling_options,
            workers=namespace.workers,
        )
