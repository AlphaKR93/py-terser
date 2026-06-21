import terser._ast as ast
from terser.transforms.suite_transformer import SuiteTransformer

ALL_BUILTIN_EXCEPTIONS = {
    'SyntaxError', 'Exception', 'ValueError', 'BaseException', 'MemoryError', 'RuntimeError', 'DeprecationWarning', 'UnicodeEncodeError', 'KeyError', 'LookupError', 'TypeError', 'BufferError',
    'ImportError', 'OSError', 'StopIteration', 'ArithmeticError', 'UserWarning', 'PendingDeprecationWarning', 'RuntimeWarning', 'IndentationError', 'UnicodeTranslateError', 'UnboundLocalError',
    'AttributeError', 'EOFError', 'UnicodeWarning', 'BytesWarning', 'NameError', 'IndexError', 'TabError', 'SystemError', 'OverflowError', 'FutureWarning', 'SystemExit', 'Warning',
    'FloatingPointError', 'ReferenceError', 'UnicodeError', 'AssertionError', 'SyntaxWarning', 'UnicodeDecodeError', 'GeneratorExit', 'ImportWarning', 'KeyboardInterrupt', 'ZeroDivisionError',
    'NotImplementedError', 'IOError', 'StandardError', 'EnvironmentError', 'VMSError', 'WindowsError',
    'ChildProcessError', 'ConnectionError', 'BrokenPipeError', 'ConnectionAbortedError', 'ConnectionRefusedError', 'ConnectionResetError', 'FileExistsError', 'FileNotFoundError', 'InterruptedError',
    'IsADirectoryError', 'NotADirectoryError', 'PermissionError', 'ProcessLookupError', 'TimeoutError', 'ResourceWarning',
    'StopAsyncIteration', 'RecursionError', 'ModuleNotFoundError', 'EncodingWarning', 'BaseExceptionGroup', 'ExceptionGroup'
}

class SimplifyRaise(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_Raise(self, node):
        node = self.generic_visit(node)
        if node.exc and isinstance(node.exc, ast.Call) and not node.exc.args and not node.exc.keywords:
            func = node.exc.func
            if isinstance(func, ast.Name) and func.id in ALL_BUILTIN_EXCEPTIONS:
                node.exc = self.add_child(func, parent=node)
        return node
