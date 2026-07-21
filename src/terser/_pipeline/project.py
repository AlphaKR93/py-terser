import os
from collections.abc import MutableSet
from typing import override, final

from anyio import Path

from .parser.ref.namespace import Namespace, SingleFileModule, Package, PackageModule
from .reporter import HeadlessProgressReporter, ProgressReporter


SUFFIXES = (".py", ".pyw",)
type NestedDict[T] = dict[str, T | NestedDict[T]]

@final
class UnresolvedModule(Namespace):
    __path: Path

    def __init__(self, root: SourceRoot, path: Path):
        super().__init__(str(path.relative_to(root.path).with_suffix("")).replace(os.path.sep, '.'))
        self.__path = path

    @property
    @override
    def path(self, /):
        return self.__path

    @override
    def resolve(self, module: str) -> str:
        raise NotImplementedError

class SourceRoot:
    __namespaces: NSResolver
    __path: Path

    __unresolved: dict[str, UnresolvedModule]

    @property
    def path(self):
        return self.__path

    def __init__(self, namespaces: NSResolver, source: Path):
        assert source.is_absolute(), "Path is not resolved yet (not an absolute path)"

        self.__namespaces = namespaces
        self.__path = source
        self.__unresolved = {}

    def register(self, path: Path):
        namespace = UnresolvedModule(self, path)
        self.__unresolved[str(namespace)] = namespace
        return namespace

    def align(self):
        aligned: NestedDict[UnresolvedModule] = {}
        resolved: dict[str, Package | SingleFileModule] = {}

        def walk(d: NestedDict[UnresolvedModule], ns: list[str]) -> NestedDict[UnresolvedModule]:
            if not len(ns):
                return d

            t: NestedDict[UnresolvedModule] | UnresolvedModule | None = d.get(c := ns.pop(0))
            if not t:
                t = d[c] = {}
            elif isinstance(t, UnresolvedModule):
                raise RuntimeError("conflict")

            t: NestedDict[UnresolvedModule]
            return walk(t, ns)

        def resolve(t: NestedDict[UnresolvedModule], parent: Package | None = None):
            current = None
            if unresolved := t.get("__init__"):
                current = Package(unresolved, parent)
                if parent:
                    parent.register(current)
                else:
                    resolved[str(current)] = current

            for k, v in t.items():
                if k == "__init__":
                    continue

                if isinstance(v, dict):
                    resolve(v, current)
                    continue

                v: UnresolvedModule
                if not current:
                    ns = SingleFileModule(v.path)
                    resolved[str(ns)] = ns
                    continue
                ns = PackageModule(v, current)
                current.register(ns)

        for k, v in self.__unresolved.items():
            ns = k.split('.')
            walk(aligned, ns[:-1])[ns[-1]] = v

        resolve(aligned)
        return resolved

class NSResolver:
    __sources: dict[str, SourceRoot]
    __namespaces: dict[str, Namespace]

    def __init__(self):
        self.__sources = {}
        self.__namespaces = {}

    def __call__(self, path: Path):
        namespace = SingleFileModule(path)
        self.__namespaces[str(namespace)] = namespace
        return namespace

    def __getitem__(self, source: Path):
        return self.__sources[str(source)]

    def register(self, source: Path):
        self.__sources[str(source)] = SourceRoot(self, source)

    def align(self):
        for root in self.__sources.values():
            self.__namespaces |= root.align()

        return self.__namespaces

class PathProvider(MutableSet[str]):
    __namespaces: dict[str, Namespace]
    __queue: set[str]
    __discarded: set[str]

    def __init__(self, paths: set[str]):
        self.__namespaces = {}
        self.__queue = set() | paths
        self.__discarded = set()

    @staticmethod
    async def __assert_file(path: Path):
        if not (await path.is_file()):
            return False

        if path.suffix not in SUFFIXES:
            return False

        return True

    @override
    def add(self, value: str, /):
        self.__queue.add(value)

    @override
    def discard(self, value: str, /):
        self.__discarded.add(value)

    @property
    def is_resolved(self, /) -> bool:
        return not len(self.__queue) and not len(self.__discarded)

    async def resolve(self, *, strict: bool = False):
        discarded, self.__discarded = {str(await Path(s).resolve()) for s in self.__discarded}, set()

        ns, queue = NSResolver(), self.__queue
        while len(queue):
            path = await Path(queue.pop()).resolve(strict=strict)
            if str(path) in discarded:
                continue

            if not (await path.exists()):
                raise FileNotFoundError(path)
            if not (await path.is_dir()):
                if not await self.__assert_file(path):
                    continue

                ns(path)
                continue

            ns.register(path)
            async for root, _, children in path.walk(follow_symlinks=not strict):
                for child in children:
                    path_ = root / child
                    if not await self.__assert_file(path_):
                        continue

                    ns[path].register(path_)

        self.__queue = set(queue)
        self.__namespaces = ns.align()

    @override
    def __contains__(self, x: str, /):
        pass

    @override
    def __len__(self):
        pass

    @override
    def __iter__(self):
        pass

    @property
    def namespace(self):
        return self.__namespaces


class ProjectMinifier:
    def __init__(
        self,
        paths: PathProvider,
        reporter: ProgressReporter | None = None,
    ):
        assert paths.is_resolved, "paths are not resolved yet"

        self.paths = paths
        self.reporter = reporter or HeadlessProgressReporter()
