from terser.ast_compat import ast
from ...parser.ref import ModuleRef, ref
from ..binding import ImportBinding, UnresolvedModuleRef


def __target_path(module_ref: ModuleRef, module: str) -> str | None:
    try:
        return module_ref.spec.resolve(module)
    except ImportError:
        return None


def __import_from_target(module_ref: ModuleRef, stmt: ast.ImportFrom, name: str | None) -> UnresolvedModuleRef:
    package = "." * stmt.level + (stmt.module or "")
    if name is None:
        return UnresolvedModuleRef(__target_path(module_ref, package))

    # `from x import y` is ambiguous: y may be a name defined in x, or a submodule of x.
    submodule = "." * stmt.level + (stmt.module + "." + name if stmt.module else name)
    return UnresolvedModuleRef(__target_path(module_ref, package), __target_path(module_ref, submodule))


def __binding_target(module_ref: ModuleRef, binding: ImportBinding) -> UnresolvedModuleRef:
    node = binding.node
    stmt = ref(node)._parent

    if isinstance(stmt, ast.ImportFrom):
        return __import_from_target(module_ref, stmt, node.name)

    assert isinstance(stmt, ast.Import)
    # A dotted import without asname only binds the root package (see NameBinder.visit_alias)
    module = node.name if node.asname is not None else binding.name
    return UnresolvedModuleRef(__target_path(module_ref, module))


def resolve_imports(module: ast.Module) -> None:
    """
    Resolve every import in `module_ref` to a module path, using only `module_ref`'s own
    Namespace. Safe to run independently per module - e.g. from a worker thread - immediately
    after `binder.bind`, without waiting on any other module in the project.

    Must run before `binder.resolve`, so `link_imports` (which needs every module in the project
    to have run this step) has a resolved path to work with for every import.
    """
    module_ref = ref(module)

    for binding in module_ref.import_targets:
        module_ref.import_targets[binding] = __binding_target(module_ref, binding)

    for stmt in module_ref.wildcard_targets:
        module_ref.wildcard_targets[stmt] = __import_from_target(module_ref, stmt, None)
