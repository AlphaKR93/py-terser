from .ref import ModuleSpec
from ast import Module
from typing import Literal

from .ref import ModuleRef


def parse(
    source: str,
    spec: ModuleSpec | str,
    mode: Literal["exec"] = "exec",
    *,
    type_comments: bool = False,
    feature_version: int | tuple[int, int] | None = None,
    optimize: Literal[-1, 0, 1, 2] = -1,
) -> tuple[Module, ModuleRef]:
    ...
