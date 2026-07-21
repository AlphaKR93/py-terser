import builtins
from typing import TYPE_CHECKING

from terser.ast_compat import ast
from ...parser.ref import ModuleRef, ref

from .binding import BuiltinBinding, NameBinding
from .util import scope_ref_global, scope_ref_nonlocal

if TYPE_CHECKING:
    from ...parser.ref import ScopedNode
    from .binding import Binding


def get_binding(name: str, namespace_ref: ScopedNode) -> Binding:
    if name in namespace_ref.globals and not isinstance(namespace_ref, ModuleRef):
        return get_binding(name, scope_ref_global(namespace_ref._ast))
    elif name in namespace_ref.nonlocals and not isinstance(namespace_ref, ModuleRef):
        return get_binding(name, scope_ref_nonlocal(namespace_ref._ast))

    for binding in namespace_ref.bindings:
        if binding.name == name:
            return binding

    if not isinstance(namespace_ref, ModuleRef):
        return get_binding(name, scope_ref_nonlocal(namespace_ref._ast))

    else:
        # This is unresolved at global scope - is it a builtin?
        if name in dir(builtins):
            if name in ['exec', 'eval', 'locals', 'globals', 'vars']:
                namespace_ref.tainted = True

            binding = BuiltinBinding(name, namespace_ref._ast)
            namespace_ref.bindings.append(binding)
            return binding

        else:
            binding = NameBinding(name)
            binding.disallow_rename()
            namespace_ref.bindings.append(binding)
            return binding


def get_binding_disallow_class_namespace_rename(name: str, namespace: ScopedNode) -> Binding:
    binding = get_binding(name, namespace)

    if isinstance(namespace, ast.ClassDef):
        # This name will become an attribute of a class, so it can't be renamed
        binding.disallow_rename()

    return binding


def resolve(node: ast.AST):
    """
    Resolve unbound names to a NameBinding

    :param node: The node to resolve names in
    """
    namespace = ref(node).namespace
    namespace_ref = ref(namespace)

    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        get_binding(node.id, namespace_ref).add_reference(node)
    elif isinstance(node, ast.Name) and node.id in namespace_ref.nonlocals:
        binding = get_binding(node.id, namespace_ref)
        binding.add_reference(node)

        if isinstance(node.ctx, ast.Store) and isinstance(namespace, ast.ClassDef):
            binding.disallow_rename()

    elif isinstance(node, ast.ClassDef) and node.name in namespace_ref.nonlocals:
        binding = get_binding_disallow_class_namespace_rename(node.name, namespace_ref)
        binding.add_reference(node)

    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in namespace_ref.nonlocals:
        binding = get_binding_disallow_class_namespace_rename(node.name, namespace_ref)
        binding.add_reference(node)

    elif isinstance(node, ast.alias):

        if node.asname is not None:
            if node.asname in namespace_ref.nonlocals:
                binding = get_binding_disallow_class_namespace_rename(node.asname, namespace_ref)
                binding.add_reference(node)

        else:
            # This binds the root module only for a dotted import
            root_module = node.name.split('.')[0]

            if root_module in namespace_ref.nonlocals:
                binding = get_binding_disallow_class_namespace_rename(root_module, namespace_ref)
                binding.add_reference(node)

                if '.' in node.name:
                    binding.disallow_rename()

    elif isinstance(node, ast.ExceptHandler) and node.name is not None:
        if isinstance(node.name, str) and node.name in namespace_ref.nonlocals:
            get_binding_disallow_class_namespace_rename(node.name, namespace_ref).add_reference(node)

    elif isinstance(node, ast.Nonlocal):
        for name in node.names:
            get_binding_disallow_class_namespace_rename(name, namespace_ref).add_reference(node)
    elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name in namespace_ref.nonlocals:
        assert node.name
        get_binding_disallow_class_namespace_rename(node.name, namespace_ref).add_reference(node)
    elif isinstance(node, ast.MatchMapping) and node.rest in namespace_ref.nonlocals:
        assert node.rest
        get_binding_disallow_class_namespace_rename(node.rest, namespace_ref).add_reference(node)

    elif isinstance(node, ast.Exec):
        scope_ref_global(node).tainted = True

    for child in ast.iter_child_nodes(node):
        resolve(child)
