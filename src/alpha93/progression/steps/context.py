from .step import Step


class BaseStepContext:
    def __enter__(self):
        return Step(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class IterableStep:
    def __init__(self, iterable):
        self.iterable = iterable

    def __iter__(self):
        for i in self.iterable:
            yield Step(self), i


class AsyncIterableStep:
    def __init__(self, iterable):
        self.iterable = iterable

    async def __aiter__(self):
        for i in self.iterable:
            yield Step(self), i
