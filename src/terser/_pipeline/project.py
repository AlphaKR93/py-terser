from .paths import PathProvider
from .reporter import HeadlessProgressReporter, ProgressReporter


class ProjectMinifier:
    def __init__(
        self,
        paths: PathProvider,
        reporter: ProgressReporter | None = None,
    ):
        assert paths.is_resolved, "paths are not resolved yet"

        self.paths = paths
        self.reporter = reporter or HeadlessProgressReporter()

    async def __call__(self, /):
        ...
