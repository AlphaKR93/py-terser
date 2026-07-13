from alpha93.commons import type_checker


if type_checker.TYPE_CHECKING:
    import ast


class InvalidTransformError(RuntimeError):
    """
    Raised when a minified module differs from the original module in an unexpected way.

    This is raised when the minifier generates source code that doesn't parse back into the
    original module (after known transformations).
    This should never occur and is a bug.
    """

    def __init__(self, exception: Exception, path: str, source: str | None, module: ast.AST):
        self.exception = exception
        self.source = source
        self.module = module
        self.path = path

    def __str__(self):
        return 'Minification was unstable! Please create an issue at https://github.com/dflook/python-minifier/issues'
