from .steps.context import BaseStepContext, IterableStep


class Reporter:
    def __call__(self, message):
        return BaseStepContext()

    def range(self, i, message):
        return IterableStep(range(i))


class BaseReporter(Reporter):
    def iter(self, iterable, message):
        from .tasks.context import IterableTaskContext
        return IterableTaskContext(iterable)

    def aiter(self, iterable, message):
        from .tasks.context import AsyncIterableTaskContext
        return AsyncIterableTaskContext(iterable)


class HeadlessReporter(BaseReporter):
    pass
