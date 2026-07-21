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

    import_targets: dict[ImportBinding, UnresolvedModuleRef | None]
    """Every ImportBinding created while binding this module, mapped to its resolved path once
    `resolve_imports` has run (None until then)"""

    wildcard_targets: dict[ast.ImportFrom, UnresolvedModuleRef | None]
    """Every `from x import *` statement in this module, mapped to its resolved path once
    `resolve_imports` has run (None until then)"""

    name: Namespace

    def __init__(self, module: ast.Module, name: Namespace):
        self.tainted = False
        self.preserved = set()
        self.import_targets = {}
        self.wildcard_targets = {}
        self.name = name

        super().__init__(module, None)  # type: ignore[invalid-type]
        self._resolve_all()

    @property
    def _parent(self):
        raise ValueError("Root node cannot have parent")

ScopedNode._klass[ast.Module] = ModuleRef
