from abc import ABC
from typing import final


@final
class Step:
    def __init__(self, reporter: ProgressReporter):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

class ProgressReporter(ABC):
    def __call__(self, task: str):
        return Step(self)

@final
class HeadlessProgressReporter(ProgressReporter):
    pass
