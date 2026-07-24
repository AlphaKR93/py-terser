if __debug__ and __import__("typing").TYPE_CHECKING:
    from typing import Final


class ProgressReporter:
    def report(self, status: str):
        pass

    def step(self, status: str):
        self.report(status)
        return Step(self)

class Step:
    __reporter: Final[ProgressReporter]

    def __init__(self, reporter: ProgressReporter):
        self.__reporter = reporter

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
