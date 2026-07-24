from python_minifier.parse.linker import ModuleImportResolver
from python_minifier._ast.tree._module import Namespace
from anyio import Path
from typing import TYPE_CHECKING

from .preprocessor import preprocess
from .._ast import ast


if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any


SOURCE_EXTENSIONS = (".py", ".pyw")


async def travel(
    *sources: str,
    strict: bool = False,
    follow_symlinks: bool = False,
) -> frozenset[tuple[Namespace, Path]]:
    paths: set[tuple[Namespace, Path]] = set()

    for source in sources:
        path = await Path(source).resolve(strict=strict)
        if not (await path.exists()):
            raise FileNotFoundError(source)
        elif not (await path.is_dir()):
            raise NotADirectoryError(source)

        async for root, _, files in path.walk(follow_symlinks=follow_symlinks):
            for file in files:
                if file.endswith(SOURCE_EXTENSIONS):
                    resolved = await root.joinpath(file).resolve(strict=strict)
                    namespace = Namespace(str(resolved.relative_to(source).with_suffix("")))
                    paths.add((namespace, path))
    return frozenset(paths)


async def process(
    args: tuple[Namespace, Path],
    compile_args: Any,
    defines: Mapping[str, bool] | None = None,
    strict: bool = False,
    /
):
    namespace, path = args
    if not (await path.exists()):
        raise FileNotFoundError(path)
    elif not (await path.is_dir()):
        raise IsADirectoryError(path)

    source, shebang = preprocess(await path.read_text("utf-8"), defines, strict)

    node = ast.parse(source, str(path), **compile_args)
    imports = ModuleImportResolver(namespace)(node)
