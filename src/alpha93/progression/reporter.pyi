from enum import IntEnum
from typing import overload, final, Any, Never, override
from collections.abc import Iterable, AsyncIterable
from abc import ABC, abstractmethod

from .steps import BaseStep, IterableStep, AsyncIterableStep, Step, StepContext
from .tasks import IterableTaskGroup, AsyncIterableTaskGroup, TaskProvider


class Reporter(ABC):
    @overload
    def __call__[T](self, message: str, iterable: None = None) -> BaseStep:
        ...
    @overload
    def __call__[T](self, message: str, iterable: Iterable[T]) -> IterableStep[T]:
        ...
    @overload
    def __call__[T](self, message: str, iterable: AsyncIterable[T]) -> AsyncIterableStep[T]:
        ...
    @overload
    def __call__[T](self, message: str, iterable: Iterable[T] | AsyncIterable[T] | None) -> Step:
        ...

    @abstractmethod
    def _step_context(self, message: str, /) -> StepContext:
        ...

    def _base_step(self, message: str) -> BaseStep:
        ...

    def _iter_step[T](self, message: str, iterable: Iterable[T]) -> IterableStep[T]:
        ...

    def _aiter_step[T](self, message: str, iterable: AsyncIterable[T]) -> AsyncIterableStep[T]:
        ...

class BaseReporter(Reporter, ABC):
    class Status(IntEnum):
        CONFIGURING = 0
        IN_PROGRESS = 1

    @abstractmethod
    def _task_provider(self, message: str, /) -> TaskProvider:
        ...

    @abstractmethod
    def prepare(self, message: str) -> BaseStep:
        ...

    @abstractmethod
    def init(self) -> None:
        ...

    def iter[T](self, iterable: Iterable[T], message: str) -> IterableTaskGroup[T]:
        ...

    def aiter[T](self, iterable: AsyncIterable[T], message: str) -> AsyncIterableTaskGroup[T]:
        ...
