from collections.abc import Iterable
from typing import final

from .steps.context import BaseStepContext, IterableStep
from .steps.step import Step
from .tasks.context import IterableTaskContext, AsyncIterableTaskContext


class Reporter:
    def __call__(self, message: str, /) -> BaseStepContext[Step]: ...

    def range(self, i: int, message: str, /) -> IterableStep[int]: ...


class BaseReporter(Reporter):
    def init(self, len: int, /) -> None: ...

    def iter[T](self, iterable: Iterable[T], message: str, /) -> IterableTaskContext[T]: ...
    def aiter[T](self, iterable: Iterable[T], message: str, /) -> AsyncIterableTaskContext[T]: ...


@final
class HeadlessReporter(BaseReporter):
    pass
