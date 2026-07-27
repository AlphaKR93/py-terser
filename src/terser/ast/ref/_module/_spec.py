from abc import ABC, abstractmethod
from typing import final, override

from anyio import Path


class ModuleSpec(ABC):
    __namespace: str

    def __init__(self, namespace: str):
        self.__namespace = namespace

    @final
    def __str__(self):
        return self.__namespace

    @final
    @property
    def name(self) -> str:
        return self.__namespace.rsplit('.', 1)[1]

    @property
    @abstractmethod
    def path(self) -> Path:
        ...

    @abstractmethod
    def resolve(self, module: str) -> str:
        ...


@final
class DummySpec(ModuleSpec):
    __name: str

    def __init__(self, name: str):
        super().__init__(f"terser.{name}")
        self.__name = name

    @override
    @property
    def path(self):
        return self.__name

    @override
    def resolve(self, module: str):
        # Cross-module linking isn't supported for a single module, but resolving an
        # import's own dotted path (for qualified_name-based checks) doesn't need it -
        # only reject imports that climb above this (nonexistent) module's root.
        if module.startswith(".."):
            raise ImportError(f"Could not resolve module: {module}")

        return module[1:] if module.startswith(".") else module


@final
class SingleFileModuleSpec(ModuleSpec):
    __path: Path

    def __init__(self, path: Path):
        super().__init__(path.with_suffix("").name)
        self.__path = path

    @override
    @property
    def path(self):
        return self.__path

    @override
    def resolve(self, module: str):
        if module.startswith(".."):
            raise ImportError(f"Could not resolve module: {module}")

        return module[1:] if module.startswith(".") else module


@final
class PackageSpec(ModuleSpec):
    __path: Path
    __parent: PackageSpec | None
    __children: dict[str, PackageSpec | PackageModuleSpec]

    def __init__(self, unresolved: ModuleSpec, parent: PackageSpec | None = None):
        assert str(unresolved).endswith(".__init__")
        super().__init__(str(unresolved).removesuffix(".__init__"))
        self.__path = unresolved.path.parent
        self.__parent = parent
        self.__children = {}

    @override
    @property
    def path(self):
        return self.__path / "__init__.py"

    @property
    def is_root_module(self) -> bool:
        return '.' not in str(self)

    @property
    def children(self) -> dict[str, ModuleSpec]:
        return self.__children  # type: ignore[ty:invalid-return-type] # wtf?

    def register(self, module: PackageSpec | PackageModuleSpec):
        self.__children[module.name] = module

    @override
    def resolve(self, module: str):
        if module == ".":
            return str(self)
        if module.startswith(".."):
            if not self.__parent:
                if not self.is_root_module:
                    raise ImportError(f"Could not resolve module: {module}")
                return module[2:]

            return self.__parent.resolve(module[1:])
        if not module.startswith("."):
            return module
        return str(self) + module

    def __getitem__(self, item: PackageModuleSpec, /) -> Path:
        return self.__path / item.name

@final
class PackageModuleSpec(ModuleSpec):
    __parent: PackageSpec
    __suffix: str

    def __init__(self, unresolved: ModuleSpec, parent: PackageSpec):
        super().__init__(str(unresolved))
        self.__parent = parent
        self.__suffix = unresolved.path.suffix

    @override
    @property
    def path(self):
        return self.__parent[self].with_suffix(self.__suffix)

    @override
    def resolve(self, module: str):
        return self.__parent.resolve(module)
