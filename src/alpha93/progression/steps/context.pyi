from collections.abc import AsyncGenerator, Generator, Iterable
from types import TracebackType
from typing import Protocol

from .step import Step


class StepContext(Protocol):
    pass

class BaseStepContext[S: Step](StepContext):
    def __enter__(self, /) -> S: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
        /
    ): ...

class IterableStep[T](StepContext):
    def __init__(self, iterable: Iterable[T]) -> None: ...
    def __iter__(self) -> Generator[tuple[Step, T]]: ...

class AsyncIterableStep[T](StepContext):
    def __init__(self, iterable: Iterable[T]) -> None: ...
    def __aiter__(self) -> AsyncGenerator[tuple[Step, T]]: ...
