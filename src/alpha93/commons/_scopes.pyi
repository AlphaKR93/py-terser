import builtins
from collections.abc import Callable, Iterable, AsyncIterable, Mapping
from types import CoroutineType
from typing import Literal, overload, Protocol, Self, Any

from commons.types import Coroutine


def constant[T](func: Callable[[], T]) -> T: ...

def dynamics(source: str, /) -> Mapping[str, Any]: ...

def throw[T: BaseException](cls: type[T], /, *args, caused_by: BaseException | None = None, **kwargs) -> T: ...

@overload
def enumerate[T](
    iterable: Iterable[T], /, start: int = 0
) -> builtins.enumerate[T]: ...
@overload
def enumerate[T](
    iterable: AsyncIterable[T], /, start: int = 0
) -> AsyncIterable[tuple[int, T]]: ...
def enumerate[T](
    iterable: Iterable[T] | AsyncIterable[T], /, start: int = 0
) -> builtins.enumerate[T] | AsyncIterable[tuple[int, T]]: ...

@overload
def catch[T: BaseException = BaseException](
    *exc_types: type[T],
    coro: Literal[False] = False,
) -> Catcher[T]: ...
@overload
def catch[T: BaseException = BaseException](
    *exc_types: type[T],
    coro: Literal[True],
) -> AsyncCatcher[T]: ...
def catch[T: BaseException = BaseException](
    *exc_types: type[T],
    coro: bool = False,
) -> Catcher[T] | AsyncCatcher[T]: ...


class Catcher[E: BaseException](Protocol):
    @overload
    def __call__[**P, T](self, fn: Callable[P, T], /) -> Callable[P, tuple[T, None]]: ...
    @overload
    def __call__[**P, T](self, fn: Callable[P, T], /) -> Callable[P, tuple[None, E]]: ...
    def __call__[**P, T](self, fn: Callable[P, T], /) -> Callable[P, tuple[T | None, None | E]]: ...


class AsyncCatcher[E: BaseException](Protocol):
    @overload
    def __call__[**P, T](self, fn: Coroutine[P, T], /) -> Coroutine[P, tuple[T, None]]: ...
    @overload
    def __call__[**P, T](self, fn: Coroutine[P, T], /) -> Coroutine[P, tuple[None, E]]: ...
    def __call__[**P, T](self, fn: Coroutine[P, T], /) -> Coroutine[P, tuple[T | None, None | E]]: ...
