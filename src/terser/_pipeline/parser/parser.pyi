from ast import Module
from os import PathLike
from typing import Any, Literal

from terser._pipeline.parser.ref import ModuleRef


def parse(
    source: str,
    path: str | PathLike[Any] | Literal["<stdin>"] | None = None,
    mode: Literal["exec", "eval", "func_type"] = "exec",
    *,
    type_comments: bool = False,
    feature_version: int | tuple[int, int] | None = None,
    optimize: Literal[-1, 0, 1, 2] = -1,
) -> tuple[Module, ModuleRef]:
    ...
