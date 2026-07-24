import python_minifier._ast as ast
from python_minifier._ast.annotation import get_parent
from python_minifier.transforms.suite_transformer import SuiteTransformer

def is_lambda_invoke_decorator(dec):
    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Lambda):
        lam = dec.func
        # lambda _: _()
        if (len(lam.args.args) == 1 and lam.args.args[0].arg == '_' and
            not lam.args.vararg and not lam.args.kwonlyargs and not lam.args.kwarg):
            if isinstance(lam.body, ast.Call) and isinstance(lam.body.func, ast.Name) and lam.body.func.id == '_':
                if not lam.body.args and not lam.body.keywords:
                    return True
    return False

def has_nonlocal(body):
    class NonlocalFinder(ast.NodeVisitor):
        def __init__(self):
            self.found = False
        def visit_Nonlocal(self, n):
            self.found = True
        def generic_visit(self, n):
            if not self.found:
                super().generic_visit(n)
    nf = NonlocalFinder()
    for stmt in body:
        nf.visit(stmt)
    return nf.found

class ReturnReplacer(ast.NodeTransformer):
    def __init__(self, name, parent_node, add_child):
        self.name = name
        self.parent_node = parent_node
        self.add_child = add_child

    def visit_Return(self, node):
        val = node.value if node.value else ast.Constant(value=None)
        assign = ast.Assign(
            targets=[ast.Name(id=self.name, ctx=ast.Store())],
            value=val
        )
        return self.add_child(assign, parent=self.parent_node)

    def visit_FunctionDef(self, node): return node
    def visit_AsyncFunctionDef(self, node): return node
    def visit_ClassDef(self, node): return node

class InlineLambdaInvoke(SuiteTransformer):
    def __init__(self):
        super().__init__()

    def __call__(self, node):
        return self.visit(node)

    def suite(self, node_list, parent):
        new_list = []
        for node in node_list:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if it has the lambda invoke decorator
                lambda_dec = None
                for dec in node.decorator_list:
                    if is_lambda_invoke_decorator(dec):
                        lambda_dec = dec
                        break

                if lambda_dec:
                    # Strip decorator
                    node.decorator_list = [d for d in node.decorator_list if d is not lambda_dec]

                    if not has_nonlocal(node.body):
                        # Hoist body, replace returns with assignments to node.name
                        replacer = ReturnReplacer(node.name, parent, self.add_child)
                        hoisted_body = []
                        for stmt in node.body:
                            new_stmt = replacer.visit(stmt)
                            if isinstance(new_stmt, list):
                                hoisted_body.extend(new_stmt)
                            elif new_stmt is not None:
                                hoisted_body.append(new_stmt)

                        # Recursively visit the hoisted body
                        hoisted_body = self.suite(hoisted_body, parent)
                        new_list.extend(hoisted_body)
                        continue

            visited = self.visit(node)
            if isinstance(visited, list):
                new_list.extend(visited)
            elif visited is not None:
                new_list.append(visited)
        return new_list

    def visit_Call(self, node):
        node = self.generic_visit(node)
        # Direct IIFE: (lambda: body)()
        if isinstance(node.func, ast.Lambda) and not node.func.args.args and not node.args:
            # Replace Call with lambda body (which is an expression)
            return self.add_child(node.func.body, parent=get_parent(node))
        return node
