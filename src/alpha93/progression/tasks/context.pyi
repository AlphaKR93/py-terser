from collections.abc import AsyncGenerator, Generator, Iterable

from .task import Task


class TaskContext:
    pass


class IterableTaskContext[T](TaskContext):
    def __init__(self, iterable: Iterable[T]) -> None: ...
    def __iter__(self) -> Generator[tuple[Task, T]]: ...


class AsyncIterableTaskContext[T](TaskContext):
    def __init__(self, iterable: Iterable[T]) -> None: ...
    def __aiter__(self) -> AsyncGenerator[tuple[Task, T]]: ...
