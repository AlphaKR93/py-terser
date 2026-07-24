import asyncio
import shutil
from typing import TYPE_CHECKING

from anyio import Path
from alpha93.progression import HeadlessReporter

from ._minify import minify, unparse
from ._pipeline import PathProvider, Pipeline, linker, mangler, transforms, tree_shake
from ._pipeline.mangler.util import preserved_names
from .ast import ref

if TYPE_CHECKING:
    import ast

    from alpha93.progression import BaseReporter

    from .ast import ModuleRef
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
        rename_modules: bool = False,
        preserve_modules: set[str] | None = None,
        entry: set[str] | None = None,
    ):
        assert path_provider.is_resolved, "paths are not resolved yet"
        assert not (rename_modules and output is None), \
            "rename_modules requires a separate output directory - it would otherwise leave the renamed file's old copy behind"

        self.__pp = path_provider
        self.config = config
        self.reporter = reporter or HeadlessReporter()
        self.output: Path | None = Path(output) if output is not None else None

        self.hoist_literals = hoist_literals
        self.rename_locals = rename_locals
        self.preserve_locals = preserve_locals or {}
        self.rename_globals = rename_globals
        self.preserve_globals = preserve_globals or {}
        self.rename_modules = rename_modules
        self.preserve_modules = preserve_modules or set()
        self.entry = entry or set()

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
        rename_modules: bool = False,
        preserve_modules: set[str] | None = None,
        entry: set[str] | None = None,
    ):
        reporter = reporter or HeadlessReporter()
        reporter.init(len=9)

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
            rename_modules=rename_modules,
            preserve_modules=preserve_modules,
            entry=entry,
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
        full_project = project

        for _, module in self.reporter.iter(collected, "Linking"):
            linker.link(module, project)

        with self.reporter("Tree-shaking"):
            entry = await self.__resolve_entry(project)
            project = tree_shake.shake(project, entry)
            collected = {module_ref.ast for module_ref in project.values()}

        with self.reporter("Mangling modules"):
            new_dotted = mangler.mangle_modules(project, self.rename_modules, self.preserve_modules, entry)

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
            tasks = [self.__dump_module(module, new_dotted) for module in collected]
            if self.output is not None:
                tasks.extend(
                    self.__copy_ffi_file(ffi_path, full_project, project, new_dotted)
                    for ffi_path in self.__pp.ffi_files
                )
            await asyncio.gather(*tasks)

    def __ffi_companion_dotted(self, ffi_path: Path) -> str | None:
        """
        The dotted module path this FFI file sits beside, if any.

        Native extensions are conventionally named after the module they belong to (optionally
        with an ABI tag before the suffix, e.g. ``foo.cpython-314-x86_64-linux-gnu.so`` or a bare
        ``foo.so``) - matching on the part before the first dot recovers that module name so the
        FFI file can be renamed/dropped in lockstep with its Python sibling.
        """

        root = None
        for r in self.__pp.roots:
            if ffi_path.is_relative_to(r):
                root = r
                break

        if root is None:
            return None

        stem = ffi_path.name.split('.', 1)[0]
        parts = ffi_path.parent.relative_to(root).parts
        return '.'.join((*parts, stem)) if parts else stem

    async def __copy_ffi_file(
        self,
        ffi_path: Path,
        full_project: dict[str, ModuleRef],
        project: dict[str, ModuleRef],
        new_dotted: dict[str, str],
    ):
        if self.output is None:
            return

        companion = self.__ffi_companion_dotted(ffi_path)

        if companion is not None and companion in full_project and companion not in project:
            # sibling module was tree-shaken away - the FFI file has no reachable consumer left
            return

        if companion is not None and companion in new_dotted:
            new_leaf = new_dotted[companion].rsplit('.', 1)[-1]
            _, _, tag = ffi_path.name.partition('.')
            new_name = f"{new_leaf}.{tag}" if tag else new_leaf
            dest = self.output.joinpath(*new_dotted[companion].split('.')[:-1], new_name)
        else:
            root = None
            for r in self.__pp.roots:
                if ffi_path.is_relative_to(r):
                    root = r
                    break

            dest = self.output / (ffi_path.relative_to(root) if root else ffi_path.name)

        await dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, str(ffi_path), str(dest))

    async def __resolve_entry(self, project: dict[str, ModuleRef]) -> set[str]:
        """Resolve `self.entry` (dotted module paths or file paths) against `project`'s modules."""

        resolved: set[str] = set()
        for value in self.entry:
            if value in project:
                resolved.add(value)
                continue

            candidate = await Path(value).resolve()
            for dotted, module_ref in project.items():
                if module_ref.spec.path == candidate:
                    resolved.add(dotted)
                    break

        return resolved

    async def __dump_module(self, module: ast.Module, new_dotted: dict[str, str]):
        spec = ref(module).spec

        if self.output is None:
            # in-place: write each module back to its own original file
            dest = spec.path
        else:
            dest = self.output / mangler.module_output_path(spec, new_dotted)
            await dest.parent.mkdir(parents=True, exist_ok=True)

        await dest.write_text(unparse(str(spec.path), None, module))
