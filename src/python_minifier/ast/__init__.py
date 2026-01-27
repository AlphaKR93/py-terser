"""
The is a backwards compatible shim for the ast module.

This is the best way to make the ast module work the same in both python 2 and 3.
This is essentially what the ast module was doing until 3.12, when it started throwing
deprecation warnings.
"""

from ast import *  # pyright: ignore[reportWildcardImportFromLibrary]


# Ideally we don't import anything else

if "TypeAlias" in globals():
    # Add n and s properties to Constant so it can stand in for Num, Str and Bytes
    Constant.n = property(lambda self: self.value, lambda self, value: setattr(self, "value", value))  # type: ignore[assignment]
    Constant.s = property(lambda self: self.value, lambda self, value: setattr(self, "value", value))  # type: ignore[assignment]

    # These classes are redefined from the ones in ast that complain about deprecation
    # They will continue to work once they are removed from ast

    class Str(Constant):  # type: ignore[no-redef]
        def __new__(cls, s, *args, **kwargs):
            return Constant(value=s, *args, **kwargs)

    class Bytes(Constant):  # type: ignore[no-redef]
        def __new__(cls, s, *args, **kwargs):
            return Constant(value=s, *args, **kwargs)

    class Num(Constant):  # type: ignore[no-redef]
        def __new__(cls, n, *args, **kwargs):
            return Constant(value=n, *args, **kwargs)

    class NameConstant(Constant):  # type: ignore[no-redef]
        def __new__(cls, *args, **kwargs):
            return Constant(*args, **kwargs)

    class Ellipsis(Constant):  # type: ignore[no-redef]
        def __new__(cls, *args, **kwargs):
            return Constant(value=literal_eval("..."), *args, **kwargs)


class _NoParent(AST):
    """A placeholder class used to indicate that a node has no parent."""

    def __repr__(self) -> str:
        return "NoParent()"


def add_parent(node: AST, parent: AST = _NoParent()):
    """
    Recursively adds a parent reference to each node in the AST.

    >>> tree = ast.parse('a = 1')
    >>> add_parent(tree)
    >>> get_parent(tree.body[0]) == tree
    True

    :param node: The current AST node.
    :param parent: The parent :class:`ast.AST` node.
    """

    node._parent = parent  # type: ignore[attr-defined]
    for child in iter_child_nodes(node):
        add_parent(child, node)


def get_parent(node: AST) -> AST:
    """
    Retrieves the parent of the given AST node.

    >>> tree = ast.parse('a = 1')
    >>> add_parent(tree)
    >>> get_parent(tree.body[0]) == tree
    True

    :param node: The AST node whose parent is to be retrieved.
    :return: The parent AST node.
    :raises ValueError: If the node has no parent.
    """

    if not hasattr(node, "_parent") or isinstance(node._parent, _NoParent):  # type: ignore[attr-defined]
        raise ValueError("Node has no parent")

    return node._parent  # type: ignore[attr-defined]


def set_parent(node: AST, parent: AST):
    """
    Replace the parent of the given AST node.

    Create a simple AST:
    >>> tree = ast.parse('a = func()')
    >>> add_parent(tree)
    >>> isinstance(tree.body[0], ast.Assign) and isinstance(tree.body[0].value, ast.Call)
    True
    >>> assign = tree.body[0]
    >>> call = tree.body[0].value
    >>> get_parent(call) == assign
    True

    Replace the parent of the call node:
    >>> tree.body[0] = call
    >>> set_parent(call, tree)
    >>> get_parent(call) == tree
    True
    >>> from python_minifier.ast_printer import print_ast
    >>> print(print_ast(tree))
    Module(body=[
        Call(Name('func'))
    ])

    :param node: The AST node whose parent is to be set.
    :param parent: The parent AST node.
    """

    node._parent = parent  # type: ignore[attr-defined]


# Create a dummy class for missing AST nodes
for _node_type in [
    "AnnAssign",
    "AsyncFor",
    "AsyncFunctionDef",
    "AsyncFunctionDef",
    "AsyncWith",
    "Bytes",
    "Constant",
    "DictComp",
    "Exec",
    "ListComp",
    "MatchAs",
    "MatchMapping",
    "MatchStar",
    "NameConstant",
    "NamedExpr",
    "Nonlocal",
    "ParamSpec",
    "SetComp",
    "Starred",
    "TryStar",
    "TypeVar",
    "TypeVarTuple",
    "TemplateStr",
    "Interpolation",
    "YieldFrom",
    "arg",
    "withitem",
]:
    if _node_type not in globals():
        globals()[_node_type] = type(_node_type, (AST,), {})
