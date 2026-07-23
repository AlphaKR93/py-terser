from alpha93.progression.tasks import Task

from ._minify import minify as __minify, unparse as __unparse
from ._pipeline import transforms
from .ast import DummySpec, ast
from .config import TransformConfig
from .project import ProjectMinifier


minify_project = ProjectMinifier.minify

def minify(
    source: str,
    config: TransformConfig,
    path: str = "<unknown>",
    /,
    preserve_shebang=True,
    prefer_single_line=False,
    **kwargs,
):
    """
    Minify a python module

    The module is transformed according to arguments.
    If all transformation arguments are False, no transformations are made to the AST, the returned string will
    parse into exactly the same module.

    Using the default arguments only transformations that are always or almost always safe are enabled.

    :param str source: The python module source code
    :param str path: The original source filename if known

    :param bool hoist_literals: If str and byte literals may be hoisted to the module level where possible.
    :param bool rename_locals: If local names may be shortened
    :param preserve_locals: Locals names to leave unchanged when rename_locals is True
    :type preserve_locals: list[str]
    :param bool rename_globals: If global names may be shortened
    :param preserve_globals: Global names to leave unchanged when rename_globals is True
    :type preserve_globals: list[str]
    :param bool preserve_shebang: Keep any shebang interpreter directive from the source in the minified output
    :param bool prefer_single_line: If semi-colons should be preferred over newlines where there is no difference in output size

    :rtype: str
    """
    module, shebang = __minify(Task(), source, DummySpec(path), config, **kwargs)

    cache = transforms.TransformCache(config)
    for _ in range(config.passes):
        for transform in transforms.__transforms__:
            if not transform.is_enabled(config) or transform.FLAGS > 4:
                continue

            module: ast.Module = transform(cache)(module)

        if not any(cache.passes.values()):
            break

    minified = __unparse(path, source, module, prefer_single_line=prefer_single_line)
    return (shebang + '\n' + minified) if preserve_shebang and shebang else minified
