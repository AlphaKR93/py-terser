from typing import TYPE_CHECKING

from terser.exceptions import InvalidTransformError
from ._pipeline import preprocessor, parser, resolver, transforms
from .ast import ast

if TYPE_CHECKING:
    from .ast.ref import ModuleSpec
    from .config import TransformConfig


async def minify(
    source: str,
    spec: ModuleSpec | str,
    config: TransformConfig,
    *,
    strict: bool = False,
    defines: dict[str, bool] | None = None,
    hoist_literals: bool = True,
    rename_locals: bool = True,
    preserve_locals: list[str] | None = None,
) -> tuple[ast.Module, str | None]:
    # TEMP: preprocess
    source, shebang = preprocessor.preprocess(source, defines, strict)

    # TEMP: parse
    module, module_ref = parser.parse(source, spec)

    # TEMP: apply transform (FLAG == 0)
    for transform in transforms.__transforms__:
        if not transform.is_enabled(config) or transform.FLAGS > 0:
            continue

        module: ast.Module = transform(config)(module)

    # TEMP: resolve
    resolver.resolve(module)
    resolver.bind(module)

    # TEMP: apply transform (FLAG <= 1)
    cache = transforms.TransformCache(config)
    for _ in range(config.passes):
        for transform in transforms.__transforms__:
            if not transform.is_enabled(config) or transform.FLAGS > 1:
                continue

            module: ast.Module = transform(cache)(module)

    # TEMP: mangle
    """
    if preserve_locals is None:
        preserve_locals = []
    elif isinstance(preserve_locals, str):
        preserve_locals = [preserve_locals]

    preserve_locals.extend(module.preserved)

    allow_rename_locals(module, rename_locals, preserve_locals)

    if hoist_literals:
        rename_literals(module)

    rename(module, prefix_globals=not rename_globals, preserved_globals=preserve_globals)
    """

    # TEMP: apply transform (FLAG <= 2)
    cache = transforms.TransformCache(config)
    for _ in range(config.passes):
        for transform in transforms.__transforms__:
            if not transform.is_enabled(config) or transform.FLAGS > 2:
                continue

            module: ast.Module = transform(cache)(module)

    try:
        module = ast.parse(module)
    except SyntaxError as exc:
        raise InvalidTransformError(exc, spec, source, module) from exc

    return module, shebang
