from typing import final, override

from alpha93.progression import Task
from alpha93.progression.reporter import BaseReporter
from alpha93.progression.steps import StepContext
from alpha93.progression.tasks import TaskProvider


@final
class HeadlessReporter(BaseReporter):
    @override
    def _step_context(self, message: str, /):
        return _EmptyStepContext()

    @override
    def _task_provider(self, message: str, /):
        return _EmptyTaskProvider()

    @override
    def init(self) -> None:
        pass

    @override
    def prepare(self, message: str):
        return self._base_step(message)


@final
class _EmptyStepContext(StepContext):
    @override
    def __enter__(self) -> None:
        pass

    @override
    def __next__(self) -> None:
        pass

    @override
    def __exit__(self, *args, **kwargs) -> None:
        pass


@final
class _EmptyTaskProvider(TaskProvider):
    @final
    class EmptyTask(Task):
        def _step_context(self, message: str, /):
            return _EmptyStepContext()

    def __enter__(self) -> None:
        pass

    def __exit__(self, *args, **kwargs):
        pass

    def task(self):
        # noinspection argument-list
        return _EmptyTaskProvider.EmptyTask()
