from terser.ast_compat import ast
from ...parser.ref import ModuleRef, ref
from ..binder.binding import Binding, ImportBinding, UnresolvedModuleRef


def _target_path(module_ref: ModuleRef, module: str) -> str | None:
    try:
        return module_ref.name.resolve(module)
    except ImportError:
        return None


def _import_from_target(module_ref: ModuleRef, stmt: ast.ImportFrom, name: str | None) -> UnresolvedModuleRef:
    package = "." * stmt.level + (stmt.module or "")
    if name is None:
        return UnresolvedModuleRef(_target_path(module_ref, package))

    # `from x import y` is ambiguous: y may be a name defined in x, or a submodule of x.
    submodule = "." * stmt.level + (stmt.module + "." + name if stmt.module else name)
    return UnresolvedModuleRef(_target_path(module_ref, package), _target_path(module_ref, submodule))


def _binding_target(module_ref: ModuleRef, binding: ImportBinding) -> UnresolvedModuleRef:
    node = binding.node
    stmt = ref(node)._parent

    if isinstance(stmt, ast.ImportFrom):
        return _import_from_target(module_ref, stmt, node.name)

    assert isinstance(stmt, ast.Import)
    # A dotted import without asname only binds the root package (see NameBinder.visit_alias)
    module = node.name if node.asname is not None else binding.name
    return UnresolvedModuleRef(_target_path(module_ref, module))


def _module_all(module_ref: ModuleRef) -> list[str] | None:
    """
    The names listed in `module_ref`'s `__all__`, or None if it has no statically resolvable
    `__all__` (either absent, or built dynamically)
    """
    for stmt in module_ref._ast.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            continue
        if stmt.targets[0].id != '__all__':
            continue
        if not isinstance(stmt.value, (ast.List, ast.Tuple)):
            return None

        names = []
        for elt in stmt.value.elts:
            if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
                return None
            names.append(elt.value)
        return names

    return None


def _has_binding(target: ModuleRef, name: str) -> bool:
    return any(binding.name == name for binding in target.bindings)


def _is_unresolved_reference(binding: Binding) -> bool:
    """Does `binding` merely record uses of an otherwise undefined name (no definition site)?"""
    return all(isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) for node in binding.references)


def mark_exports(module_ref: ModuleRef) -> None:
    """
    Flag the module-level bindings that make up `module_ref`'s public interface - importable via
    `from module_ref import name` or `from module_ref import *`, regardless of whether the
    project actually imports them.

    Only needs `module_ref`'s own AST/bindings. Safe to run independently per module, immediately
    after `binder.bind`.
    """

    all_ = _module_all(module_ref)
    exported_names = set(all_) if all_ is not None else {
        binding.name for binding in module_ref.bindings if not binding.name.startswith('__')
    }

    for binding in module_ref.bindings:
        if binding.name in exported_names:
            binding.exported = True


def resolve_imports(module_ref: ModuleRef) -> None:
    """
    Resolve every import in `module_ref` to a module path, using only `module_ref`'s own
    Namespace. Safe to run independently per module - e.g. from a worker thread - immediately
    after `binder.bind`, without waiting on any other module in the project.

    Must run before `binder.resolve`, so `link_imports` (which needs every module in the project
    to have run this step) has a resolved path to work with for every import.
    """

    for binding in module_ref.import_targets:
        module_ref.import_targets[binding] = _binding_target(module_ref, binding)

    for stmt in module_ref.wildcard_targets:
        module_ref.wildcard_targets[stmt] = _import_from_target(module_ref, stmt, None)


def _link_alias(binding: ImportBinding, unresolved: UnresolvedModuleRef, project: dict[str, ModuleRef]) -> None:
    package_target = project.get(unresolved.path) if unresolved.path is not None else None

    if unresolved.submodule_path is None:
        # plain `import x[.y]` - unambiguous, the binding always refers to the module itself
        binding.target = package_target
        return

    name = binding.node.name  # the imported attribute/submodule name
    if package_target is not None and _has_binding(package_target, name):
        binding.target = package_target
        binding.target_name = name
        return

    submodule_target = project.get(unresolved.submodule_path) if unresolved.submodule_path is not None else None
    if submodule_target is not None:
        binding.target = submodule_target
        return

    if package_target is not None:
        # x resolves within the project, but y is neither a binding nor a submodule of it,
        # e.g. provided dynamically through x's __getattr__ (PEP 562)
        binding.target = package_target
        binding.disallow_rename()

    # else: x itself is stdlib / third-party - leave binding.target as None


def _link_wildcard(module_ref: ModuleRef, stmt: ast.ImportFrom, unresolved: UnresolvedModuleRef, project: dict[str, ModuleRef]) -> None:
    target = project.get(unresolved.path) if unresolved.path is not None else None

    if target is None:
        # Can't enumerate an external module's exports statically
        module_ref.tainted = True
        return

    exported = {binding.name for binding in target.bindings if binding.exported}

    for index, binding in enumerate(module_ref.bindings):
        if binding.name not in exported or not _is_unresolved_reference(binding):
            continue  # unused, or shadowed by a real local definition - the wildcard doesn't apply

        upgraded = ImportBinding(binding.name, stmt)
        for node in binding.references:
            upgraded.add_reference(node)

        upgraded.target = target
        upgraded.target_name = binding.name  # exported implies target actually has this binding

        module_ref.bindings[index] = upgraded


def link_imports(module_ref: ModuleRef, project: dict[str, ModuleRef]) -> None:
    """
    Resolve every import's target and expand wildcard imports, using the other modules in the
    project. Must run after every module in the project has run `resolve_imports`, `mark_exports`
    and `binder.resolve` (the latter so undefined-but-used names have their fallback binding, for
    `_link_wildcard` to upgrade).

    :param module_ref: The module to link imports for
    :param project: Every module in the project, keyed by resolved module path
    """

    for binding, unresolved in module_ref.import_targets.items():
        _link_alias(binding, unresolved, project)

    for stmt, unresolved in module_ref.wildcard_targets.items():
        _link_wildcard(module_ref, stmt, unresolved, project)
