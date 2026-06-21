import sys
from dataclasses import dataclass, field

@dataclass
class TerserConfig:
    # Threading
    threads: int = 4
    transform_passes: int = 3          # how many times Transform stage repeats

    # Pipeline toggles
    fold_constants: bool = True
    optimize: bool = True              # remove-asserts + remove-debug merged
    defines: dict[str, bool] = field(default_factory=dict)
    no_tree_shake: bool = False

    # Transform toggles (all True by default unless noted)
    remove_docstrings: bool = False
    strict_docstrings: bool = True     # preserve module-level docstrings
    remove_annotations: bool = True
    remove_variable_annotations: bool = True
    remove_return_annotations: bool = True
    remove_argument_annotations: bool = True
    remove_class_attribute_annotations: bool = False
    remove_explicit_inherits: bool = True  # RemoveExplicitInherits (formerly remove_object_base)
    remove_type_stmt: bool = True
    remove_trailing_returns: bool = True
    simplify_posargs: bool = True
    simplify_dynamic_attrs: bool = True
    simplify_fstring: bool = True
    simplify_early_exit: bool = True
    simplify_raise: bool = True
    simplify_if_stmt: bool = True
    convert_to_ternary: bool = True
    convert_to_lambda: bool = True
    hoist_literals: bool = True
    inline_functions: bool = True
    inline_int_flags: bool = True
    cleanup_imports: bool = True

    # Mangle
    rename_locals: bool = True
    rename_globals: bool = False
    preserve_locals: list[str] = field(default_factory=list)
    preserve_globals: list[str] = field(default_factory=list)
    ignore_all: bool = False

    # Output
    prefer_single_line: bool = True
    preserve_shebang: bool = True
    obfuscation_map: dict | None = None
    rename_map: dict | None = None

    # Cross-module obfuscation
    module_name_map: dict | None = None
    current_module_name: str | None = None
    user_modules: set[str] = field(default_factory=set)

    # sys constants for EnvironmentConstantTransformer
    version_info: tuple = field(default_factory=lambda: sys.version_info[:3])
    platform: str = sys.platform

