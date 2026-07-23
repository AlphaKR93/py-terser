from tqdm import tqdm

from alpha93.progression.reporter import BaseReporter
from alpha93.progression.steps.context import BaseStepContext, IterableStep
from alpha93.progression.tasks.context import AsyncIterableTaskContext, IterableTaskContext
from alpha93.progression.tasks.task import Task


class _TqdmStepContext(BaseStepContext):
    def __init__(self, message, position):
        self._bar = tqdm(total=1, desc=message, position=position, leave=False)

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)
        self._bar.update(1)
        self._bar.close()


class _TqdmIterableStep(IterableStep):
    def __init__(self, i, message, position):
        super().__init__(tqdm(range(i), desc=message, position=position, leave=False))


class TqdmTask(Task):
    def __init__(self, position):
        self._position = position

    def __call__(self, message):
        return _TqdmStepContext(message, self._position)

    def range(self, i, message):
        return _TqdmIterableStep(i, message, self._position)


class _TqdmIterableTaskContext(IterableTaskContext):
    def __init__(self, iterable, message, position):
        super().__init__(tqdm(iterable, desc=message, position=position, leave=False))
        self._position = position

    def __iter__(self):
        for value in self.iterable:
            yield TqdmTask(self._position + 1), value


class _TqdmAsyncIterableTaskContext(AsyncIterableTaskContext):
    def __init__(self, iterable, message, position):
        super().__init__(tqdm(iterable, desc=message, position=position, leave=False))
        self._position = position

    async def __aiter__(self):
        for value in self.iterable:
            yield TqdmTask(self._position + 1), value


class TqdmReporter(BaseReporter):
    def __init__(self, position=0):
        self._position = position

    def __call__(self, message):
        return _TqdmStepContext(message, self._position)

    def range(self, i, message):
        return _TqdmIterableStep(i, message, self._position)

    def iter(self, iterable, message):
        return _TqdmIterableTaskContext(iterable, message, self._position)

    def aiter(self, iterable, message):
        return _TqdmAsyncIterableTaskContext(iterable, message, self._position)
