from .task import Task


class TaskContext:
    pass


class IterableTaskContext:
    def __init__(self, iterable):
        self.iterable = iterable

    def __iter__(self):
        for i in self.iterable:
            yield Task(), i


class AsyncIterableTaskContext:
    def __init__(self, iterable):
        self.iterable = iterable

    async def __aiter__(self):
        for i in self.iterable:
            yield Task(), i
