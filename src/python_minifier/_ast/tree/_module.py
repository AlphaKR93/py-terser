from __future__ import annotations  # FIXME: ty complains

from abc import ABC
from typing import TYPE_CHECKING, final

from .. import ast
from ._namespace import Namespace
from ._root import Node, ASTNode


if TYPE_CHECKING:
    from os import PathLike
    from typing import Final


class Namespaced(Node, ABC):
    namespace: Namespace
    path: PathLike


class Package(Namespaced, ABC):
    parent: Package | None


@final
class NamespacePackage(Package):
    parent: NamespacePackage | None


class Source(ASTNode[ast.Module], Namespaced, ABC):
    source: str
    imports: set[str]


@final
class RegularPackage(Package, Source):
    pass


@final
class Module(Source):
    parent: RegularPackage

    body: list[ast.stmt]
    type_ignores: list[ast.TypeIgnore]
