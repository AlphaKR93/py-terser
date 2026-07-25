import os
import shutil
from typing import TYPE_CHECKING

import anyio
from anyio import AsyncFile, CapacityLimiter, Path, to_thread

from alpha93.progression import HeadlessReporter

from ._minify import minify, unparse
from ._pipeline import PathProvider, Pipeline, linker, mangler, transforms
from ._pipeline.mangler.util import preserved_names
from .ast import ref

if TYPE_CHECKING:
    import ast
    from collections.abc import Callable, Coroutine
    from typing import Any

    from alpha93.progression import BaseReporter, Task
    from terser.ast.ref import ModuleRef, ModuleSpec

    from .config import TransformConfig

    type Awaitable[T] = Coroutine[Any, Any, T]


async def _read_async(path: Path, /, *, limiter: CapacityLimiter) -> str:
    # noinspection bad-argument-type
    source_fp = await to_thread.run_sync(path._path.open, 'r', limiter=limiter)
    source_io = AsyncFile(source_fp, limiter=limiter)
    try:
        # noinspection bad-return
        return await source_io.read()
    finally:
        await source_io.aclose()

async def _write_async(path: Path, source: str, /, *, limiter: CapacityLimiter):
    # noinspection bad-argument-type
    source_fp = await to_thread.run_sync(path._path.open, 'w', limiter=limiter)
    source_io = AsyncFile(source_fp, limiter=limiter)
    try:
        # noinspection bad-argument-type
        await source_io.write(source)
    finally:
        await source_io.aclose()

class ProjectMinifier(Pipeline):
    def __init__(
        self,
        path_provider: PathProvider,
        config: TransformConfig,
        /,
        reporter: BaseReporter,
        output: Path | None = None,
        workers: int | None = None,
        *,
        rename_locals: bool = True,
        preserve_locals: dict[str, list[str]] | None = None,
        rename_globals: bool = False,
        preserve_globals: dict[str, list[str]] | None = None,
        hoist_literals: bool = True,
        prefer_single_line: bool = True,
    ):
        assert path_provider.is_resolved, "paths are not resolved yet"

        self.__config = config
        self.__output = output

        self.__pp = path_provider
        self.__reporter = reporter
        self.__limiter = CapacityLimiter(total_tokens=workers or int(
                (getattr(os, "process_cpu_count", os.cpu_count)() or 1) * 1.6
        ))

        self.rename_locals = rename_locals
        self.preserve_locals = preserve_locals or {}
        self.rename_globals = rename_globals
        self.preserve_globals = preserve_globals or {}
        self.hoist_literals = hoist_literals
        self.prefer_single_line = prefer_single_line

    @classmethod
    async def minify(
        cls,
        config: TransformConfig,
        paths: set[str],
        /,
        reporter: BaseReporter | None = None,
        output: Path | None = None,
        *args,
        **kwargs
    ):
        # noinspection argument-list,bad-assignment
        reporter: BaseReporter = reporter or HeadlessReporter()

        if len(paths) > 1 and not output:
            raise ValueError("Multiple paths are given, but no output path specified")

        with reporter.prepare("Resolving paths"):
            pp = PathProvider(paths)
            await pp.resolve()

        await cls(pp, config, reporter, output, *args, **kwargs)()

    async def __call__(self, /):
        with self.__reporter.prepare("Calculating task graph"):
            from terser.utils.cli_helper import TqdmDebugTaskGraph
            m, f = len(self.__pp), len(self.__pp.ffi_files)

            tg = TqdmDebugTaskGraph(
                TqdmDebugTaskGraph.Task(m,
                    TqdmDebugTaskGraph.Step(),
                    TqdmDebugTaskGraph.Step(),
                    TqdmDebugTaskGraph.Step(),
                    TqdmDebugTaskGraph.IterableStep(self.__config.passes),
                    TqdmDebugTaskGraph.Step(),
                ),
                TqdmDebugTaskGraph.IterableStep(m),
                TqdmDebugTaskGraph.IterableStep(m * self.__config.passes),
                TqdmDebugTaskGraph.IterableStep(m + 1),
                TqdmDebugTaskGraph.Task(m + f),
            )
            del TqdmDebugTaskGraph, m, f

        with self.__reporter as reporter:
            reporter.init(task_graph=tg)
            del tg

            modules, project = await self.__minify_modules()

            for module in self.__reporter("Linking", modules):
                linker.link(module, project)

            # Each module gets its own TransformCache - cache.passes tracks per-transform
            # "did this change the module" for SuiteTransformer.__new__'s skip-unchanged
            # optimization, which is meaningless if shared across independent module trees.
            caches = [transforms.TransformCache(self.__config) for _ in modules]
            modules_len = len(modules)
            for j in self.__reporter("Applying transforms", range(self.__config.passes * modules_len)):
                i = j % modules_len
                modules[i] = transforms.apply_pass(caches[i], modules[i], transforms.__transforms__, 2)

                if not i and not any(any(cache.passes.values()) for cache in caches):
                    break

            # for richer progress bar support
            iter_ = iter(self.__reporter("Mangling", range(-1, modules_len)))
            next(iter_)
            mangler.mangle_globals(project, self.rename_globals, self.preserve_globals)

            for i in iter_:
                cache = caches[i]
                for transform in transforms.__transforms__:
                    if not transform.is_enabled(self.__config) or transform.FLAGS > 4:
                        continue

                    modules[i] = transform(cache)(modules[i])

            await self.__dump_results(modules)

    async def __minify_modules(self, /) -> tuple[list[ast.Module], dict[str, ModuleRef]]:
        def __run(task: Task, source: str, spec: ModuleSpec, /):
            local = sorted(preserved_names(str(spec), self.preserve_locals))
            return minify(
                task, source, spec,
                self.__config,
                hoist_literals=self.hoist_literals,
                rename=self.rename_locals,
                preserved_names=local,
            )

        modules: list = [None] * len(self.__pp)
        async def __worker(i: int, task: Task, spec: ModuleSpec, /):
            source = await _read_async(spec.path, limiter=self.__limiter)
            module, _ = await to_thread.run_sync(__run, task, source, spec, limiter=self.__limiter)
            modules[i] = module
            task.done()

        async with anyio.create_task_group() as tg:
            # TODO: Cleanup this shit
            j = len(self.__pp) - 1
            for i, (task, spec) in enumerate(self.__reporter.iter(self.__pp.iter(), "Compiling modules")):
                # noinspection async-call
                t = tg.start_soon(__worker, i, task, spec)

                if i == j:
                    await t.wait()  # forcefully blocks the generator from finishing

        if not all(modules):
            raise RuntimeError("Failed to compile all modules")

        modules: list[ast.Module]
        project: dict[str, ModuleRef] = {str(ref(x).spec): ref(x) for x in modules}
        return modules, project

    async def __dump_results(self, modules: list[ast.Module], /):
        async def module(node: ast.Module, /):
            spec = ref(node).spec

            if self.__output is None:
                dest = spec.path
            else:
                dest = self.__output / str(spec).replace('.', Path.parser.sep)
                dest = dest.with_suffix(spec.path.suffix)
                await dest.parent.mkdir(parents=True, exist_ok=True)

            source = await to_thread.run_sync(unparse, str(spec.path), None, node, self.prefer_single_line)
            await _write_async(dest, source, limiter=self.__limiter)

        async def binary(path: Path, /):
            assert self.__output

            root = None
            for r in self.__pp.roots:
                if path.is_relative_to(r):
                    root = r
                    break

            dest = self.__output / (path.relative_to(root) if root else path.name)
            await dest.parent.mkdir(parents=True, exist_ok=True)
            await to_thread.run_sync(shutil.copy2, str(path), str(dest))

        def wrap[T](func: Callable[[T], Awaitable[None]]) -> Callable[[T], Callable[[Task], Awaitable[None]]]:
            def wrapper(t: T) -> Callable[[Task], Awaitable[None]]:
                async def runner(task: Task, /):
                    await func(t)
                    task.done()
                return runner
            return wrapper

        tasks = set(map(wrap(module), modules)) | set(map(wrap(binary), self.__pp.ffi_files))
        async with anyio.create_task_group() as tg:
            j = len(tasks) - 1
            for i, (task, func) in enumerate(self.__reporter.iter(tasks, "Writing output")):
                # noinspection async-call
                t = tg.start_soon(func, task)

                if i == j:
                    await t.wait()
