from typing import TYPE_CHECKING, final

from terser.ast_compat import ast
from ._scoped import ScopedNode

if TYPE_CHECKING:
    from .namespace import Namespace
    from terser._pipeline.linker.binder.binding import ImportBinding, UnresolvedModuleRef


@final
class _Root(ast.AST):
    def __repr__(self):
        return "Root()"


@final
class ModuleRef(ScopedNode[ast.Module]):
    tainted: bool
    preserved: set[str]
    imports: dict[str, ast.AST]

    import_bindings: set[ImportBinding]
    """Every ImportBinding created while binding this module, for the cross-module linking step"""

    wildcard_imports: list[ast.ImportFrom]
    """`from x import *` statements, deferred until the target module's exports are known"""

    wildcard_targets: list[tuple[ast.ImportFrom, UnresolvedModuleRef]]
    """The resolved path for each of `wildcard_imports`, filled in by `resolve_import_paths`"""

    name: Namespace

    def __init__(self, module: ast.Module, name: Namespace):
        self.tainted = False
        self.preserved = set()
        self.imports = {}
        self.import_bindings = set()
        self.wildcard_imports = []
        self.wildcard_targets = []
        self.name = name

        super().__init__(module, None)  # type: ignore[invalid-type]
        self._resolve_all()

    @property
    def _parent(self):
        raise ValueError("Root node cannot have parent")

ScopedNode._klass[ast.Module] = ModuleRef
