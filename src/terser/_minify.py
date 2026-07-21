from typing import TYPE_CHECKING

from terser.exceptions import InvalidTransformError
from ._pipeline import preprocessor, parser, resolver
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
    hoist_literals=True,
    rename_locals=True,
    preserve_locals=None,
) -> ast.Module:
    # TEMP: preprocess
    source, shebang = preprocessor.preprocess(source, defines, strict)

    # TEMP: parse
    module, module_ref = parser.parse(source, spec)

    # TEMP: apply transform (FLAG == 0)

    # TEMP: resolve
    resolver.resolve(module)
    resolver.bind(module)

    # TEMP: apply transform (FLAG <= 1)
    for _ in range(config.passes):
        pass

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
    for _ in range(config.passes):
        pass

    try:
        module = ast.parse(module)
    except SyntaxError as exc:
        raise InvalidTransformError(exc, spec, source, module) from exc

    return module
