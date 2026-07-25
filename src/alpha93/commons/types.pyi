from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol
from types import CoroutineType


type AwaitableOr[T] = T | Awaitable[T]
type SequenceOr[T] = T | Sequence[T]

type Coroutine[**P, T] = Callable[P, Awaitable[T] | CoroutineType[Any, Any, T]]
type Decorator[F, V] = Callable[[F], V]
type Wrapper[T] = Decorator[T, T]
type Transformer[**P, T, U] = Decorator[Callable[P, T], Callable[P, U]]

class Constructor[T, **P](Protocol):
    def __call__(self, /, *args: P.args, **kwargs: P.kwargs) -> T: ...

class __TypedGetter:
    class Typed[T]:
        def getattr[U](self, obj, name: str, default: U = ...) -> T: ...

    def __getitem__[T](self, item: type[T]) -> Typed[T]: ...

typed: __TypedGetter

__all__ = (
    "AwaitableOr",
    "SequenceOr",
    "Coroutine",
    "Decorator",
    "Wrapper",
    "Transformer",
    "Constructor",
    "typed",
)
