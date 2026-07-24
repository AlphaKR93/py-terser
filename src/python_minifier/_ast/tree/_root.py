from abc import ABC
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ast import AST


class Node(ABC):
    pass

class ASTNode[T : AST](ABC):
    _ast: T
