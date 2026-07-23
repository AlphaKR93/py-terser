import asyncio
from typing import TYPE_CHECKING

from anyio import Path
from alpha93.progression import HeadlessReporter

from ._minify import minify, unparse
from ._pipeline import PathProvider, Pipeline, linker, mangler, transforms
from ._pipeline.mangler.util import preserved_names
from .ast import ref

if TYPE_CHECKING:
    import ast

    from alpha93.progression import BaseReporter

    from .config import TransformConfig


class ProjectMinifier(Pipeline):
    def __init__(
        self,
        path_provider: PathProvider,
        config: TransformConfig,
        reporter: BaseReporter,
        output: str | Path | None,
        *,
        hoist_literals: bool = True,
        rename_locals: bool = True,
        preserve_locals: dict[str, list[str]] | None = None,
        rename_globals: bool = False,
        preserve_globals: dict[str, list[str]] | None = None,
    ):
        assert path_provider.is_resolved, "paths are not resolved yet"

        self.__pp = path_provider
        self.config = config
        self.reporter = reporter or HeadlessReporter()
        self.output: Path | None = Path(output) if output is not None else None

        self.hoist_literals = hoist_literals
        self.rename_locals = rename_locals
        self.preserve_locals = preserve_locals or {}
        self.rename_globals = rename_globals
        self.preserve_globals = preserve_globals or {}

    @classmethod
    async def minify(
        cls,
        paths: set[str],
        config: TransformConfig,
        output: str | Path | None,
        reporter: BaseReporter | None = None,
        /,
        *,
        hoist_literals: bool = True,
        rename_locals: bool = True,
        preserve_locals: dict[str, list[str]] | None = None,
        rename_globals: bool = False,
        preserve_globals: dict[str, list[str]] | None = None,
    ):
        reporter = reporter or HeadlessReporter()
        reporter.init(len=7)

        with reporter("Resolving paths"):
            pp = PathProvider(paths)
            await pp.resolve()

        await cls(
            pp, config, reporter, output,
            hoist_literals=hoist_literals,
            rename_locals=rename_locals,
            preserve_locals=preserve_locals,
            rename_globals=rename_globals,
            preserve_globals=preserve_globals,
        )()

    async def __minify_module(self, task, spec) -> ast.Module:
        source = await spec.path.read_text()
        preserve_locals = sorted(preserved_names(str(spec), self.preserve_locals))
        module, _ = await asyncio.to_thread(
            minify, task, source, spec, self.config,
            hoist_literals=self.hoist_literals,
            rename_locals=self.rename_locals,
            preserve_locals=preserve_locals,
        )
        return module

    async def __minify_modules(self) -> list[ast.Module]:
        pairs = [
            (task, spec)
            async for task, spec in self.reporter.aiter(self.__pp.iter(), "Parsing modules")
        ]
        total = len(pairs) or 1
        done = 0

        async def run(task, spec) -> ast.Module:
            nonlocal done
            module = await self.__minify_module(task, spec)
            done += 1
            self.reporter.progress(done / total)
            return module

        return await asyncio.gather(*(run(task, spec) for task, spec in pairs))

    async def __call__(self, /):
        collected = set(await self.__minify_modules())
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
            mangler.mangle_globals(project, self.rename_globals, self.preserve_globals)

        for _, module in self.reporter.iter(collected, "Applying transforms"):
            for transform in transforms.__transforms__:
                if not transform.is_enabled(self.config) or transform.FLAGS > 4:
                    continue

                module: ast.Module = transform(cache)(module)

        with self.reporter("Writing output"):
            await asyncio.gather(*(self.__dump_module(module) for module in collected))

    async def __dump_module(self, module: ast.Module):
        spec = ref(module).spec

        if self.output is None:
            # in-place: write each module back to its own original file
            dest = spec.path
        else:
            root = self.__pp.root_for(spec)
            dest = self.output / (spec.path.relative_to(root) if root else spec.path.name)
            await dest.parent.mkdir(parents=True, exist_ok=True)

        await dest.write_text(unparse(str(spec.path), None, module))
