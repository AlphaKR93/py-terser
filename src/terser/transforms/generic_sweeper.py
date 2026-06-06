import terser.ast_compat as ast
from terser.transforms.suite_transformer import SuiteTransformer

class GenericSweeper(SuiteTransformer):
    """
    Strip TypeVar declarations and PEP 695 type parameter brackets from classes and functions.
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_ClassDef(self, node):
        if hasattr(node, 'type_params') and node.type_params:
            node.type_params = []
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if hasattr(node, 'type_params') and node.type_params:
            node.type_params = []
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_Assign(self, node):
        # Check if right-hand side is a TypeVar, TypeVarTuple, or ParamSpec call
        if isinstance(node.value, ast.Call):
            func = node.value.func
            is_typevar = False
            if isinstance(func, ast.Name) and func.id in ('TypeVar', 'TypeVarTuple', 'ParamSpec'):
                is_typevar = True
            elif isinstance(func, ast.Attribute) and func.attr in ('TypeVar', 'TypeVarTuple', 'ParamSpec') and isinstance(func.value, ast.Name) and func.value.id == 'typing':
                is_typevar = True
            
            if is_typevar:
                return None
        return node

    def suite(self, node_list, parent):
        cleaned = []
        for node in node_list:
            visited = self.visit(node)
            if visited is not None:
                if isinstance(visited, list):
                    cleaned.extend(visited)
                else:
                    cleaned.append(visited)
        return cleaned
