from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, final

from .reporter import Reporter

from types import TracebackType

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator


class TaskProvider(ABC):
    @abstractmethod
    def __enter__(self) -> None:
        ...

    @abstractmethod
    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ):
        ...

    @abstractmethod
    def task(self) -> Task:
        ...

    @final
    def __next__(self) -> Task:
        return self.task()


class TaskGroup(ABC):
    # noinspection property-definition
    _ctx = property(lambda self: self.__ctx)

    def __init__(self, provider: TaskProvider):
        self.__ctx = provider


class IterableTaskGroup[T](TaskGroup):
    def __init__(self, provider: TaskProvider, iterable: Iterable[T]):
        super().__init__(provider)
        self.__iterable = iterable

    def __iter__(self) -> Iterator[tuple[Task, T]]:
        with self._ctx:
            for i in self.__iterable:
                yield next(self._ctx), i


class AsyncIterableTaskGroup[T](TaskGroup):
    def __init__(self, provider: TaskProvider, iterable: AsyncIterable[T]):
        super().__init__(provider)
        self.__iterable = iterable

    async def __aiter__(self) -> AsyncIterator[tuple[Task, T]]:
        with self._ctx:
            async for i in self.__iterable:
                yield next(self._ctx), i


class Task(Reporter, ABC):
    pass
