from tqdm import tqdm

from alpha93.progression.reporter import BaseReporter
from alpha93.progression.steps.context import BaseStepContext
from alpha93.progression.steps.step import Step
from alpha93.progression.tasks.task import Task


class TqdmReporter(BaseReporter):
    """
    Reports progress on a single overall tqdm bar, split into `len` equal-weight phases.

    Individual steps/tasks don't get their own bars - with many modules processed
    concurrently, one bar per step/task made dozens of bars race for the same terminal
    lines and appear to spawn endlessly. Instead, the one bar fills in fractionally as a
    phase's items are consumed (for synchronous `iter`/`range`), and its description
    tracks the current phase's message - concurrently-processed work handed out via
    `aiter` has no meaningful per-item completion signal to show here, so that phase just
    displays its message and the bar jumps to the next phase once it's done.
    """

    def __init__(self):
        self._bar = None
        self._phase = 0
        self._total = 0

    def init(self, len):
        self._total = len
        self._bar = tqdm(total=len, leave=True)

    def _enter_phase(self, message) -> bool:
        """Advance to the next phase; returns True if this is the last one."""

        if self._bar is None:
            return False

        self._bar.set_description(message)
        self._bar.n = self._phase
        self._bar.refresh()
        self._phase += 1
        return self._phase >= self._total

    def _set_fraction(self, fraction: float):
        if self._bar is None:
            return
        self._bar.n = (self._phase - 1) + fraction
        self._bar.refresh()

    def _finish(self):
        if self._bar is None:
            return
        self._bar.n = self._total
        self._bar.refresh()
        self._bar.close()
        self._bar = None

    def __call__(self, message):
        return _StepContext(self, self._enter_phase(message))

    def range(self, i, message):
        return _FractionalStep(self, i, self._enter_phase(message))

    def iter(self, iterable, message):
        return _FractionalTaskIter(self, list(iterable), self._enter_phase(message))

    def aiter(self, iterable, message):
        return _PassthroughTaskAiter(self, iterable, self._enter_phase(message))


class _StepContext(BaseStepContext):
    def __init__(self, reporter: TqdmReporter, is_last: bool):
        self._reporter = reporter
        self._is_last = is_last

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)
        if self._is_last:
            self._reporter._finish()


class _FractionalStep:
    def __init__(self, reporter: TqdmReporter, i: int, is_last: bool):
        self._reporter = reporter
        self._i = i
        self._is_last = is_last

    def __iter__(self):
        total = self._i or 1
        for idx in range(self._i):
            yield Step(self), idx
            self._reporter._set_fraction((idx + 1) / total)
        if self._is_last:
            self._reporter._finish()


class _FractionalTaskIter:
    def __init__(self, reporter: TqdmReporter, items: list, is_last: bool):
        self._reporter = reporter
        self._items = items
        self._is_last = is_last

    def __iter__(self):
        total = len(self._items) or 1
        for idx, value in enumerate(self._items):
            yield Task(), value
            self._reporter._set_fraction((idx + 1) / total)
        if self._is_last:
            self._reporter._finish()


class _PassthroughTaskAiter:
    def __init__(self, reporter: TqdmReporter, iterable, is_last: bool):
        self._reporter = reporter
        self._iterable = iterable
        self._is_last = is_last

    async def __aiter__(self):
        for value in self._iterable:
            yield Task(), value
        if self._is_last:
            self._reporter._finish()
