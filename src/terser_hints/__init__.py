from typing import TypeVar

_T = TypeVar("_T")


def preserve_docstring(obj: _T, /) -> _T:
    """
    Marker decorator: tells terser to keep this class/function's docstring
    even when docstring removal is otherwise enabled. Detected statically,
    a no-op at runtime.
    """
    return obj


def preserve_annotations(obj: _T, /) -> _T:
    """
    Marker decorator: tells terser to keep this function/class's type annotations
    even when annotation removal is otherwise enabled. Detected statically,
    a no-op at runtime.
    """
    return obj


def constant(fn):
    """
    Marker decorator: tells terser this function is only ever called once, to
    compute a constant - immediately call it and rebind its name to the result,
    the same as the `@lambda _: _()` idiom. Detected statically; at runtime this
    just calls `fn` once and returns its result.
    """
    return fn()


__all__ = ("preserve_docstring", "preserve_annotations", "constant")
