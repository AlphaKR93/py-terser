from typing import TypeVar

_T = TypeVar("_T")


def preserve_docstring(obj: _T, /) -> _T:
    """
    Marker decorator: tells terser to keep this class/function's docstring
    even when docstring removal is otherwise enabled. Detected statically,
    a no-op at runtime.
    """
    return obj


__all__ = ("preserve_docstring",)
