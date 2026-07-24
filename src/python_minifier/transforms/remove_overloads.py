import python_minifier._ast as ast
from python_minifier.transforms.suite_transformer import SuiteTransformer

def is_overload(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == 'overload':
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == 'overload' and isinstance(dec.value, ast.Name) and dec.value.id == 'typing':
            return True
    return False

def is_abstract(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == 'abstractmethod':
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == 'abstractmethod' and isinstance(dec.value, ast.Name) and dec.value.id == 'abc':
            return True
    return False

class RemoveOverloads(SuiteTransformer):
    def __init__(self):
        super().__init__()

    def __call__(self, node):
        return self.visit(node)

    def suite(self, node_list, parent):
        # Group functions by name
        func_groups = {}
        for node in node_list:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_groups.setdefault(node.name, []).append(node)

        # Identify which names have overloads
        to_remove = set()
        for name, group in func_groups.items():
            has_any_overload = any(is_overload(f) for f in group)
            if has_any_overload:
                # Validate overload rules
                overloads = [f for f in group if is_overload(f)]
                non_overloads = [f for f in group if not is_overload(f)]

                # Exclude abstract methods from non-overload count check if there's no implementation,
                # but wait: "No non-overload implementation exists (excluding @abstractmethod)."
                # So we count implementations that are not overloads. If there are none, we check if there's an abstractmethod.
                # If there are 0 non-overload implementations, or more than 1 non-overload implementations, we raise an error.
                # Let's count implementations (which are not abstract and not overload)
                impls = [f for f in non_overloads if not is_abstract(f)]

                if len(impls) == 0:
                    # Let's check if there is an abstractmethod
                    abstracts = [f for f in non_overloads if is_abstract(f)]
                    if len(abstracts) == 0:
                        raise RuntimeError(f"No non-overload implementation exists for overload function '{name}'.")
                    elif len(abstracts) > 1:
                        raise RuntimeError(f"Multiple non-overload abstract implementations exist for overload function '{name}'.")
                elif len(impls) > 1:
                    raise RuntimeError(f"Multiple non-overload implementations exist for overload function '{name}'.")

                # All overloads are to be removed
                to_remove.update(overloads)

        # Filter the suite
        new_list = []
        for node in node_list:
            if node in to_remove:
                continue
            visited = self.visit(node)
            if isinstance(visited, list):
                new_list.extend(visited)
            elif visited is not None:
                new_list.append(visited)
        return new_list
