import threading
import weakref

from tqdm import tqdm

from alpha93.progression.reporter import BaseReporter
from alpha93.progression.steps.context import BaseStepContext, IterableStep
from alpha93.progression.tasks.context import AsyncIterableTaskContext, IterableTaskContext
from alpha93.progression.tasks.task import Task

# tqdm's internal position bookkeeping isn't safe to share across threads without a
# shared lock - without this, bars created concurrently (one per asyncio.to_thread
# worker) race and stomp on each other's lines.
tqdm.set_lock(threading.RLock())


class _PositionPool:
    """
    Hands out `position` values for concurrently-alive tqdm bars.

    Reusing a fixed position across concurrently running bars (e.g. one per module
    minified in a worker thread) makes tqdm redraw over itself and appear to spawn
    endless duplicate bars. Each concurrent user gets its own position, released back
    to the pool once it's no longer referenced.
    """

    def __init__(self, base: int):
        self._free: list[int] = []
        self._next = base
        self._lock = threading.Lock()

    def acquire(self) -> int:
        with self._lock:
            if self._free:
                return self._free.pop()
            position = self._next
            self._next += 1
            return position

    def release(self, position: int):
        with self._lock:
            self._free.append(position)


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


def _pooled_task(pool: _PositionPool) -> TqdmTask:
    position = pool.acquire()
    task = TqdmTask(position)
    weakref.finalize(task, pool.release, position)
    return task


class _TqdmIterableTaskContext(IterableTaskContext):
    def __init__(self, iterable, message, position):
        super().__init__(tqdm(iterable, desc=message, position=position, leave=False))
        self._pool = _PositionPool(position + 1)

    def __iter__(self):
        for value in self.iterable:
            yield _pooled_task(self._pool), value


class _TqdmAsyncIterableTaskContext(AsyncIterableTaskContext):
    def __init__(self, iterable, message, position):
        super().__init__(tqdm(iterable, desc=message, position=position, leave=False))
        self._pool = _PositionPool(position + 1)

    async def __aiter__(self):
        for value in self.iterable:
            yield _pooled_task(self._pool), value


class TqdmReporter(BaseReporter):
    def __init__(self, position=0):
        self._position = position
        self._overall = None

    def init(self, len):
        self._overall = tqdm(total=len, desc="Overall", position=self._position, leave=True)
        self._position += 1

    def _tick(self):
        if self._overall is None:
            return
        self._overall.update(1)
        if self._overall.n >= self._overall.total:
            self._overall.close()

    def __call__(self, message):
        self._tick()
        return _TqdmStepContext(message, self._position)

    def range(self, i, message):
        self._tick()
        return _TqdmIterableStep(i, message, self._position)

    def iter(self, iterable, message):
        self._tick()
        return _TqdmIterableTaskContext(iterable, message, self._position)

    def aiter(self, iterable, message):
        self._tick()
        return _TqdmAsyncIterableTaskContext(iterable, message, self._position)
