from typing import TYPE_CHECKING

from alpha93.progression import HeadlessReporter

from ._minify import minify
from ._pipeline import PathProvider, Pipeline, linker, mangler, transforms
from .ast import ref

if TYPE_CHECKING:
    import ast
    from collections.abc import AsyncGenerator

    from alpha93.progression import BaseReporter

    from .config import TransformConfig


class ProjectMinifier(Pipeline):
    def __init__(self, path_provider: PathProvider, config: TransformConfig, reporter: BaseReporter):
        assert path_provider.is_resolved, "paths are not resolved yet"

        self.__pp = path_provider
        self.config = config
        self.reporter = reporter or HeadlessReporter()

    @classmethod
    async def minify(cls, paths: set[str], config: TransformConfig, reporter: BaseReporter | None = None, /):
        reporter = reporter or HeadlessReporter()
        reporter.init(len=6)

        with reporter("Resolving paths"):
            pp = PathProvider(paths)
            await pp.resolve()

        await cls(pp, config, reporter)()

    async def __minify_modules(self) -> AsyncGenerator[tuple[ast.Module, str | None]]:
        async for task, spec in self.reporter.aiter(self.__pp.iter(), "Parsing modules"):
            source = await spec.path.read_text()
            yield minify(task, source, spec, self.config)

    async def __call__(self, /):
        collected = {x async for x, _ in self.__minify_modules()}   # TODO: multi-threaded
        project = {str(ref(x).spec): ref(x) for x in collected}

        for _, module in self.reporter.iter(collected, "Linking"):
            linker.link(module, project)

        cache = transforms.TransformCache(self.config)
        for _ in self.reporter.range(self.config.passes, "Applying transforms"):
            for module in collected:
                for transform in transforms.__transforms__:
                    if not transform.is_enabled(self.config) or transform.FLAGS > 2:
                        continue

                    module: ast.Module = transform(cache)(module)

            if not any(cache.passes.values()):
                break

        with self.reporter("Mangling"):
            mangler.mangle_globals(project)

        for _, module in self.reporter.iter(collected, "Applying transforms"):
            for transform in transforms.__transforms__:
                if not transform.is_enabled(self.config) or transform.FLAGS > 4:
                    continue

                module: ast.Module = transform(cache)(module)
