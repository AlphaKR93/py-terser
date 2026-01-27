"""
Remove Call nodes that are only used to raise exceptions with no arguments

If a Raise statement is used on a Name and the name refers to an exception, it is automatically instantiated with no arguments
We can remove any Call nodes that are only used to raise exceptions with no arguments and let the Raise statement do the instantiation.
When printed, this essentially removes the brackets from the exception name.

We can't generally know if a name refers to an exception, so we only do this for builtin exceptions
"""

import python_minifier.ast as ast

from python_minifier.rename.binding import BuiltinBinding


# These are always exceptions, in every version of python
builtin_exceptions = [
    "SyntaxError",
    "Exception",
    "ValueError",
    "BaseException",
    "MemoryError",
    "RuntimeError",
    "DeprecationWarning",
    "UnicodeEncodeError",
    "KeyError",
    "LookupError",
    "TypeError",
    "BufferError",
    "ImportError",
    "OSError",
    "StopIteration",
    "ArithmeticError",
    "UserWarning",
    "PendingDeprecationWarning",
    "RuntimeWarning",
    "IndentationError",
    "UnicodeTranslateError",
    "UnboundLocalError",
    "AttributeError",
    "EOFError",
    "UnicodeWarning",
    "BytesWarning",
    "NameError",
    "IndexError",
    "TabError",
    "SystemError",
    "OverflowError",
    "FutureWarning",
    "SystemExit",
    "Warning",
    "FloatingPointError",
    "ReferenceError",
    "UnicodeError",
    "AssertionError",
    "SyntaxWarning",
    "UnicodeDecodeError",
    "GeneratorExit",
    "ImportWarning",
    "KeyboardInterrupt",
    "ZeroDivisionError",
    "NotImplementedError",
    # These are exceptions in 3.3+
    "ChildProcessError",
    "ConnectionError",
    "BrokenPipeError",
    "ConnectionAbortedError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "FileExistsError",
    "FileNotFoundError",
    "InterruptedError",
    "IsADirectoryError",
    "NotADirectoryError",
    "PermissionError",
    "ProcessLookupError",
    "TimeoutError",
    "ResourceWarning",
    "StopAsyncIteration",  # 3.5+
    "RecursionError",  # 3.5+
    "ModuleNotFoundError",  # 3.6+
]

# These are exceptions in 3.10+
builtin_exceptions_3_10 = ["EncodingWarning"]

# These are exceptions in 3.11+
builtin_exceptions_3_11 = [
    "BaseExceptionGroup",
    "ExceptionGroup",
    "BaseExceptionGroup",
]


def _remove_empty_call(binding):
    assert isinstance(binding, BuiltinBinding)

    for name_node in binding.references:
        # For this to be a builtin, all references must be name nodes as it is not defined anywhere
        assert isinstance(name_node, ast.Name)
        assert isinstance(name_node.ctx, ast.Load)

        if not isinstance(ast.get_parent(name_node), ast.Call):
            # This is not a call
            continue
        call_node = ast.get_parent(name_node)

        if not isinstance(ast.get_parent(call_node), ast.Raise):
            # This is not a raise statement
            continue
        raise_node = ast.get_parent(call_node)

        if len(call_node.args) > 0 or len(call_node.keywords) > 0:
            # This is a call with arguments
            continue

        # This is an instance of the exception being called with no arguments
        # let's replace it with just the name, cutting out the Call node

        if raise_node.exc is call_node:
            raise_node.exc = name_node
        elif raise_node.cause is call_node:
            raise_node.cause = name_node
        ast.set_parent(name_node, raise_node)


def remove_no_arg_exception_call(module):
    assert isinstance(module, ast.Module)

    for binding in module.bindings:
        if not isinstance(binding, BuiltinBinding):
            continue

        if binding.is_redefined():
            continue

        if binding.name in builtin_exceptions:
            # We can remove any calls to builtin exceptions
            _remove_empty_call(binding)

    return module
