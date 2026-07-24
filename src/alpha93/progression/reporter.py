from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING

from alpha93.progression.steps import BaseStep, IterableStep, AsyncIterableStep
from alpha93.progression.tasks import IterableTaskGroup, AsyncIterableTaskGroup

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Iterable
    from typing import Any


class Reporter(ABC):
    def __call__(self, message: str, iterable = None):
        if iterable is None:
            return self._base_step(message)

        iterable: Any
        return self._iter_step(message, iterable) if hasattr(iterable, '__iter__') \
            else self._aiter_step(message, iterable)

    @abstractmethod
    def _step_context(self, message: str, /):
        ...

    def _base_step(self, message: str):
        return BaseStep(self._step_context(message))

    def _iter_step(self, message: str, iterable):
        return IterableStep(self._step_context(message), iterable)

    def _aiter_step(self, message: str, iterable):
        return AsyncIterableStep(self._step_context(message), iterable)


class BaseReporter(Reporter, ABC):
    class Status(IntEnum):
        CONFIGURING = 0
        IN_PROGRESS = 1

    @abstractmethod
    def _task_provider(self, message: str, /):
        ...

    @abstractmethod
    def prepare(self, message: str):
        ...

    @abstractmethod
    def init(self):
        ...

    def iter(self, iterable: Iterable, message: str):
        return IterableTaskGroup(self._task_provider(message), iterable)

    def aiter(self, iterable: AsyncIterable, message: str):
        return AsyncIterableTaskGroup(self._task_provider(message), iterable)
