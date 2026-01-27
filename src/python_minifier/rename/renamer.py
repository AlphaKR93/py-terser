import python_minifier.ast as ast

from .binding import NameBinding
from .name_generator import name_filter
from .util import is_namespace


def all_bindings(node):
    """
    All bindings in a module

    :param node: The module to get bindings in
    :type node: :class:`ast.AST`
    :rtype: Iterable[ast.AST, Binding]

    """

    if is_namespace(node):
        for binding in node.bindings:
            yield node, binding

    for child in ast.iter_child_nodes(node):
        for namespace, binding in all_bindings(child):
            yield namespace, binding


def sorted_bindings(module):
    """
    All bindings in a modules sorted by descending number of references

    :param module: The module to get bindings in
    :type module: :class:`ast.AST`
    :rtype: Iterable[ast.AST, Binding]

    """

    def comp(tup):
        _namespace, binding = tup
        return binding.new_mention_count()

    return sorted(all_bindings(module), key=comp, reverse=True)


def reservation_scope(namespace, binding):
    """
    Get the namespaces that are in the bindings reservation scope

    Returns the namespace nodes the binding name must be resolvable in

    :param namespace: The local namespace of a binding
    :type namespace: :class:`ast.AST`
    :param binding: The binding to get the reservation scope for
    :type binding: Binding
    :rtype: set[ast.AST]

    """

    namespaces = {namespace}

    for node in binding.references:
        curr = node.namespace
        while curr is not namespace:
            namespaces.add(curr)

            # [수정됨] 모듈 경계에 도달하거나, 더 이상 부모가 없으면 중단 (무한 루프 방지)
            if isinstance(curr, ast.Module):
                break
            if not hasattr(curr, "namespace") or curr.namespace is curr:
                break

            curr = curr.namespace

    return namespaces


def add_assigned(node):
    """
    Add the assigned_names attribute to namespace nodes in a module

    :param node: The module to add the assigned_names attribute to
    :type node: :class:`ast.Module`

    """

    if is_namespace(node):
        # 이미 초기화되어 있다면 덮어쓰지 않도록 할 수도 있지만,
        # 기본 로직은 호출 시 초기화하는 것입니다.
        # NameAssigner 호출 시 제어합니다.
        node.assigned_names = set()

    for child in ast.iter_child_nodes(node):
        add_assigned(child)


def reserve_name(name, reservation_scope):
    """
    Reserve a name in a reservation scope

    :param str name: The name to reserve
    :param reservation_scope:
    :type reservation_scope: Iterable[:class:`ast.AST`]

    """

    for namespace in reservation_scope:
        # [Fix] Only reserve in active namespaces (nodes that are still in the AST)
        # If a node was removed by a previous transform (like RemoveDebug), it won't have assigned_names.
        if hasattr(namespace, "assigned_names"):
            namespace.assigned_names.add(name)


class UniqueNameAssigner(object):
    """
    Assign new names to renamed bindings

    Assigns a unique name to every binding
    """

    def __init__(self):
        self.name_generator = name_filter()
        self.names = []

    def available_name(self):
        return next(self.name_generator)

    def __call__(self, module):
        assert isinstance(module, ast.Module)

        for _namespace, binding in sorted_bindings(module):
            if binding.allow_rename:
                binding.new_name = self.available_name()

        return module


class NameAssigner(object):
    """
    Assign new names to renamed bindings

    This assigner creates a name 'reservation scope' containing each namespace a binding is referenced in, including
    transitive namespaces. Bindings are then assigned the first available name that has no references in their
    reservation scope. This means names will be reused in sibling namespaces, and shadowed where possible in child
    namespaces.

    Bindings are assigned names in order of most references, with names assigned shortest first.

    """

    def __init__(self, name_generator=None):
        self.name_generator = name_generator if name_generator is not None else name_filter()
        self.names = []

    def iter_names(self):
        for name in self.names:
            yield name

        while True:
            name = next(self.name_generator)
            self.names.append(name)
            yield name

    def available_name(self, reservation_scope, prefix=""):
        """
        Search for the first name that is not in reservation scope
        """

        for name in self.iter_names():
            if self.is_available(prefix + name, reservation_scope):
                return prefix + name

        return None

    def is_available(self, name, reservation_scope):
        """
        Is a name unreserved in a reservation scope

        :param str name: the name to check availability of
        :param reservation_scope: The scope to check
        :type reservation_scope: Iterable[:class:`ast.AST`]
        :rtype: bool

        """
        # [Fix] Check availability only in active namespaces
        # Nodes removed by transforms (e.g. RemoveDebug) will not have assigned_names attribute.
        for namespace in reservation_scope:
            assigned = getattr(namespace, "assigned_names", None)
            if assigned is not None and name in assigned:
                return False
        return True

    def __call__(self, module, prefix_globals, reserved_globals=None):
        assert isinstance(module, ast.Module)

        # [수정됨] assigned_names가 없는 경우에만 초기화합니다.
        # 프로젝트 전체 Minify 시, 미리 초기화된 상태를 유지해야 교차 참조 시 이름 충돌을 방지할 수 있습니다.
        if not getattr(module, "assigned_names", None):
            add_assigned(module)

        for namespace, binding in all_bindings(module):
            if binding.reserved is not None:
                scope = reservation_scope(namespace, binding)
                reserve_name(binding.reserved, scope)

        if reserved_globals is not None:
            # 모듈이 이미 초기화되어 있어도 reserved_globals는 추가해야 합니다.
            if not hasattr(module, "assigned_names"):
                # 안전장치 (위에서 처리되지만)
                module.assigned_names = set()
            for name in reserved_globals:
                module.assigned_names.add(name)

        def should_rename(binding, name, scope):
            if binding.should_rename(name):
                return True

            # It's no longer efficient to do this rename

            if isinstance(binding, NameBinding):
                # Check that the original name is still available

                if binding.reserved == binding.name:
                    # We already reserved it (this is probably an arg)
                    return False

                if not self.is_available(binding.name, scope):
                    # The original name has already been assigned to another binding,
                    # so we need to rename this anyway.
                    return True

            return False

        for namespace, binding in sorted_bindings(module):
            scope = reservation_scope(namespace, binding)

            if binding.allow_rename:
                if isinstance(namespace, ast.Module) and prefix_globals:
                    name = self.available_name(scope, prefix="_")
                else:
                    name = self.available_name(scope)

                if should_rename(binding, name, scope):
                    binding.rename(name)
                else:
                    # Any existing name will become reserved
                    binding.disallow_rename()

            if binding.name is not None:
                reserve_name(binding.name, scope)

        # [New] Generate export aliases for preserved globals that were renamed
        exports = []
        # We only handle module-level bindings for this feature
        for binding in module.bindings:
            if isinstance(binding, NameBinding) and getattr(binding, "export_as", None):
                if binding.name != binding.export_as:
                    # The binding was renamed, but needs to be exported with its original name
                    exports.append((binding.export_as, binding.name))

        # Sort by original name to ensure deterministic output
        exports.sort(key=lambda x: x[0])

        for original, new_name in exports:
            module.body.append(
                ast.Assign(
                    targets=[ast.Name(id=original, ctx=ast.Store())], value=ast.Name(id=new_name, ctx=ast.Load())
                )
            )

        return module


def rename(module, prefix_globals=False, preserved_globals=None, allow_unicode=False):
    NameAssigner(name_generator=name_filter(allow_unicode=allow_unicode))(module, prefix_globals, preserved_globals)
