from dataclasses import dataclass, field
from typing import Literal


@dataclass()
class RemoveAnnotationOptions:
    """Options that affect how annotations are removed"""

    remove_variable_annotations: bool = True
    """Remove variable annotations"""

    remove_return_annotations: bool = True
    """Remove return annotations"""

    remove_argument_annotations: bool = True
    """Remove argument annotations"""

    remove_attribute_annotations: bool = False
    """Remove class attribute annotations"""


@dataclass()
class RemoveDocstringOptions:
    """Options that affect how docstrings are removed"""

    also_modules: bool = False
    """Also remove module-level docstrings"""


@dataclass()
class TransformConfig:
    passes: int = 5
    optimize: Literal[-1, 0, 1, 2] = -1

    contracts: list[str] = field(default_factory=lambda: [
        "typing.cast(_, value) -> value",
        "typing.assert_never(_) -> None",
        "typing.assert_type(x, _) -> x",
    ])

    apply_contracts: bool = True

    remove_literal_statements: bool = False
    """Remove statements consisting of a single literal that does nothing"""

    combine_imports: bool = True
    """Combine adjacent import statements where possible"""

    remove_annotations: bool | RemoveAnnotationOptions = True
    """Options that affect how annotations are removed"""

    remove_explicit_base: bool = True
    """Remove explicit base classes"""

    remove_explicit_return_none: bool = True
    """Replace explicit `return None` statements with bare `return`"""

    fold_constants: bool = True
    """Evaluate and shrink constant literals"""

    remove_debug: bool = True
    """Remove conditional statements that test __debug__ is True (part of FoldConstants)"""

    remove_asserts: bool = True

    convert_pass: bool = True
    """Remove or convert `pass` statements to the smallest literal statement, like `0`"""

    unfold_iife_lambdas: bool = True
    """Inline immediately-invoked no-arg lambda calls, e.g. `(lambda: x)()` -> `x`"""

    remove_type_statements: bool = False
    """Remove `type X = ...` alias statements. Unsafe by default: this runs pre-transform
    (before even per-module name resolution), so it can't tell whether the alias is
    actually imported/used by another module at runtime - only enable this if no `type`
    statement in the project is relied on outside of typing contexts"""

    convert_early_exits: bool = True
    """Merge `if cond: return a` followed by `return b` into `return a if cond else b`"""

    convert_to_inline: bool = True
    """Convert `if cond: func(x)` to `cond and func(x)`, and if/else statements to a conditional expression"""

    convert_to_lambda: bool = True
    """Convert single-expression functions to a lambda assignment"""

    ### requires binding
    remove_dummy_assignments: bool = True
    """Remove self-assignments like `x = x`"""

    remove_docstrings: bool | RemoveDocstringOptions = False
    """Options that affect how docstrings are removed"""

    respect_all: bool = False
    """When cleaning up unused imports, also remove unused module-level imports not listed in `__all__`"""

    cleanup_local_imports: bool = True
    """Remove unused local imports, and unused global imports if `respect_all`"""

    remove_typing_decorators: bool = True
    """Remove `@typing.override`/`@typing.final` decorators"""

    remove_overloads: bool = True
    """Remove `@typing.overload`-decorated stub definitions. Always on when `remove_typing_decorators` is set"""

    remove_generics: bool = True
    """Remove bare (non-parametrized) `Generic` base classes"""

    remove_typing_classes: bool = False
    """Remove bare `Protocol` base classes (unless `@typing.runtime_checkable`). Unsafe across module
    boundaries: a stripped class loses Protocol semantics even where another module subclasses it
    together with `Protocol[...]`, which raises `TypeError` at class-definition time."""

    convert_typing_constructors: bool = True
    """Convert simple `NamedTuple`/`TypedDict` class definitions to `namedtuple`/`dict` constructors"""

    convert_typing_extensions: bool = True
    """Convert `typing_extensions` imports to `typing` where the symbol is stable there"""

    convert_dynamic_attribute_access: bool = True
    """Convert `getattr`/`setattr` calls with a constant, valid identifier name to attribute access"""

    remove_empty_exc_brackets: bool = True
    """Remove brackets with empty arguments from built-in exception raise statements"""

    ### mangle-sensitive transforms
    convert_posargs: bool = True
    """Convert positional-only arguments to normal arguments"""

    remove_dunder_all: bool = False
    """Remove the top-level `__all__` assignment. Unsafe across module boundaries: another
    module doing `from this_module import *` relies on `__all__` (falling back to "no names"
    when every top-level name is prefixed with an underscore), which a per-module pass run
    before project-wide linking has no way to see."""
