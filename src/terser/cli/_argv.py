from typing import TYPE_CHECKING, Annotated

from alpha93.argparse import MutuallyExclusive
from alpha93.commons.pydantic import dataclasses
from pydantic import BaseModel, ConfigDict, Field

from terser.config import TransformConfig, RemoveAnnotationOptions

if TYPE_CHECKING:
    from argparse import Namespace


_config = ConfigDict(use_attribute_docstrings=True)
PydanticTransformOptions = dataclasses.to_model(TransformConfig)


class OutputOptions(BaseModel):
    model_config = _config

    output: str | None = "stdout"
    """Path to write minified output."""

    in_place: bool = False
    """Overwrite existing files."""


class ManglingOptions(BaseModel):
    model_config = _config

    hoist_literals: bool = True
    """Replace frequently used constant literals with variables that have shorter name."""

    rename_locals: bool = True
    """Mangle local (including nonlocal) names"""

    preserve_locals: Annotated[set[str], Field(default_factory=set)]
    """Comma-separated list of local name references that will not be mangled"""

    rename_globals: bool = False
    """Mangle global names"""

    preserve_globals: Annotated[set[str], Field(default_factory=set)]
    """Comma-separated list of global name references that will not be mangled"""


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
        if namespace.remove_annotations and not all(remove_annotations.__dict__.values()):
            raise ValueError
        transform_options = TransformConfig(
            optimize=namespace.optimize,
            remove_literal_statements=namespace.remove_literal_statements,
            combine_imports=namespace.combine_imports,
            remove_annotations=namespace.remove_annotations or remove_annotations,
            remove_explicit_base=namespace.remove_explicit_base,
            remove_explicit_return_none=namespace.remove_explicit_return_none,
            fold_constants=namespace.fold_constants,
            remove_debug=namespace.remove_debug,
            convert_pass=namespace.convert_pass,
            remove_empty_exc_brackets=namespace.remove_empty_exc_brackets,
            convert_posargs=namespace.convert_posargs,
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
        )
