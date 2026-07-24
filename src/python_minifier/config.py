from python_minifier import RemoveAnnotationsOptions
import sys
import dataclasses


TYPE_CHECKING = False


def field(doc: str | None = None, **kwargs):
    kwargs["metadata"] = kwargs.get("metadata", {})
    kwargs["metadata"]["doc"] = doc

    if sys.version_info >= (3, 14):
        return dataclasses.field(doc=doc, **kwargs)
    else:
        return dataclasses.field(**kwargs)



@dataclasses.dataclass(frozen=True)
class TerserConfig:
    threads: int = field(
        doc="Number of worker threads to use for parallel tasks",
        default=4
    )
    passes: int = field(
        doc="Number of times the transform stage repeats",
        default=5
    )
    defines: dict[str, bool] = field(
        doc="Define preprocessor variables",
        default_factory=dict
    )
    target_version: tuple[int, int] = field(
        default_factory=lambda: sys.version_info[:3]
    )

    ### Name Mangling
    rename_locals: bool = field(
        doc="Whether to shortening of local names",
        default=True
    )
    preserve_locals: set[str] = field(
        doc="Comma separated list of local names that will not be shortened",
        default_factory=set
    )
    rename_globals: bool = field(
        doc="Whether to shortening of global names",
        default=False
    )
    preserve_globals: set[str] = field(
        doc="Comma separated list of local names that will not be shortened",
        default_factory=set
    )
    ignore_all: bool = field(
        doc="Ignore __all__ when renaming globals",
        default=False
    )

    ### Transform
    optimize: bool = field(
        doc="Remove `assert` statements and `__debug__`, `TYPE_CHECKING` checks",
        default=False,
    )
    hoist_literals: bool = field(
        doc="Replace constant literals used multiple times with variables with shorten name",
        default=True
    )
    cleanup_imports: bool = field(
        doc="Remove unused imports and combine adjacent import statements",
        default=True
    )
    remove_literal_statements: bool = field(
        doc="Remove constant literal statements that are just a literal",
        default=True
    )
    remove_docstrings: bool = field(
        doc="Remove docstrings",
        default=False
    )
    preserve_module_docstrings: bool = field(
        doc="Preserve module-level docstrings. This will only affect when --remove-docstring is enabled",
        default=True
    )
    remove_explicit_inherits: bool = field(
        doc="Remove explicit inherits from base class list",
        default=True
    )
    remove_explicit_return_none: bool = field(
        doc="Replace explicit return None with a bare return",
        default=True
    )
    remove_trailing_returns: bool = field(
        doc="Remove explicit trailing return None (or bare return)",
        default=True
    )
    remove_pass: bool = field(
        doc="Replace pass statement with shortest constant literal statement",
        default=True
    )
    remove_exc_brackets: bool = field(
        doc="Remove explicit brackets when raising without arguments",
        default=True
    )
    remove_type_statement: bool = field(
        doc="Remove PEP 695 type statements",
        default=True
    )
    remove_posargs: bool = field(
        doc="Remove positional-only parameter in arguments",
        default=True
    )
    simplify_fstring: bool = field(
        doc="Simplify f-strings",
        default=True
    )
    simplify_early_exit: bool = field(
        doc="Simplify early exit else/elif blocks",
        default=True
    )
    simplify_if_statement: bool = field(
        doc="Simplify single expression if statements",
        default=True
    )
    simplify_functions: bool = field(
        doc="Simplify single expression functions",
        default=True
    )
    inline_functions: bool = True

    simplify_dynattrs: bool = field(
        doc="Simplify dynamic attributes (getattr/setattr)",
        default=False
    )
    fold_constants: bool = field(
        doc="Evaluate constant literal expressions",
        default=False
    )
    inline_int_flags: bool = field(
        doc="Inline IntFlag when available",
        default=False
    )
    remove_annotations: RemoveAnnotationsOptions = field(
        default_factory=RemoveAnnotationsOptions,
    )

    ### Output
    prefer_oneline: bool = field(
        doc="Prefer multiple statements on a single line separated by semicolons instead of newlines, where there's "
            "no difference in output size. It'll always a single line if the size changes due to indentation.",
        default=False
    )
    tree_shaking: bool = field(
        doc="Remove unused modules",
        default=False
    )
    obfuscation_map: dict | None = None
    rename_map: dict | None = None
