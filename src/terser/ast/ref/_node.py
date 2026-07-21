from typing import TYPE_CHECKING, ClassVar

from terser.ast.ast import AST as Node, iter_child_nodes

if TYPE_CHECKING:
    from ast import AST
    from typing import Final


_FIELD = "__AST_NodeRef__ref__"


class NodeRef[T: AST]:
    _klass: ClassVar[dict[type[AST], type[NodeRef]]] = {}
    _ast: Final[T]
    _parent: AST

    def __init__(self, node: T, parent: AST):
        setattr(node, _FIELD, self)

        self._ast = node
        if parent:  # INTENDED: for ModuleRef
            self._parent = parent

    @classmethod
    def new(cls, node: AST, parent: AST):
        if cls_ := NodeRef._klass.get(type(node)):
            return cls_(node, parent)

        return cls(node, parent)

    def _resolve_all(self):
        for node in iter_child_nodes(self._ast):
            NodeRef.new(node, self._ast)._resolve_all()

    def __repr__(self):
        r = {i: f"{j.__class__.__name__}(...)" if isinstance(j, Node) else repr(j) for i, j in self.__dict__.items()}
        return f"{self.__class__.__name__}({', '.join([f"{k}={v}" for k, v in r.items()])})"


ref = lambda node: getattr(node, _FIELD)
