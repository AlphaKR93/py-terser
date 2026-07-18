from abc import ABC, abstractmethod
from typing import final, override

from anyio import Path


class Namespace(ABC):
    __namespace: str

    def __init__(self, namespace: str):
        self.__namespace = namespace

    @abstractmethod
    def resolve(self, module: str) -> str:
        ...

    @property
    @abstractmethod
    def path(self, /) -> Path:
        ...

    @final
    @property
    def name(self, /) -> str:
        return self.__namespace.rsplit('.', 2)[1]

    @final
    def __str__(self):
        return self.__namespace

@final
class SingleFileModule(Namespace):
    __path: Path

    def __init__(self, path: Path):
        super().__init__(path.with_suffix("").name)
        self.__path = path

    @override
    def resolve(self, module: str) -> str:
        if module.startswith(".."):
            raise ImportError(f"Could not resolve module: {module}")

        return module[1:] if module.startswith(".") else module

    @property
    @override
    def path(self, /):
        return self.__path

@final
class NamespacePackage(Namespace):
    __path: Path
    __children: dict[str, Package]

    def __init__(self, path: Path):
        super().__init__(path.name[:-1])
        self.__children = {}

    def register(self, module: Package):
        self.__children[module.name] = module

    @override
    def resolve(self, module: str) -> str:
        if module == ".":
            return str(self)
        if module.startswith("..."):
            raise ImportError(f"Could not resolve module: {module}")
        if module.startswith(".."):
            return module[2:]
        return str(self) + module

    @property
    @override
    def path(self, /):
        return self.__path

    def __getitem__(self, item: PackageModule) -> Path:
        return self.__path / item.name

@final
class Package(Namespace):
    __path: Path
    __parent: Package | NamespacePackage | None
    __children: dict[str, Package | PackageModule]

    def __init__(self, unresolved: Namespace, parent: Package | NamespacePackage | None = None):
        assert str(unresolved).endswith(".__init__")
        super().__init__(str(unresolved).rstrip(".__init__"))
        self.__path = unresolved.path.parent
        self.__parent = parent
        self.__children = {}

    def register(self, module: Package | PackageModule):
        self.__children[module.name] = module

    @override
    def resolve(self, module: str) -> str:
        if module == ".":
            return str(self)
        if module.startswith(".."):
            if not self.__parent:
                if not self.is_root_module:
                    raise ImportError(f"Could not resolve module: {module}")
                return module[2:]

            return self.__parent.resolve(module[1:])
        return str(self) + module

    @property
    @override
    def path(self, /):
        return self.__path / "__init__.py"

    @property
    def is_root_module(self) -> bool:
        return '.' not in str(self)

    def __getitem__(self, item: PackageModule) -> Path:
        return self.__path / item.name

@final
class PackageModule(Namespace):
    __parent: Package
    __suffix: str

    def __init__(self, unresolved: Namespace, parent: Package):
        super().__init__(str(unresolved))
        self.__parent = parent
        self.__suffix = unresolved.path.suffix.strip('.')

    @property
    @override
    def path(self, /):
        return self.__parent[self].with_suffix(self.__suffix)

    @override
    def resolve(self, module: str) -> str:
        return self.__parent.resolve(module)
