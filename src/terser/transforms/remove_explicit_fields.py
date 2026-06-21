import terser._ast as ast
from terser.transforms.suite_transformer import SuiteTransformer

def should_skip_class_fields(node):
    if hasattr(node, 'decorator_list'):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id in ('dataclass', 'preserve_typing'):
                return True
            if isinstance(dec, ast.Attribute) and dec.attr in ('dataclass', 'preserve_typing'):
                return True
            # Also check if it's a call like dataclasses.dataclass()
            if isinstance(dec, ast.Call):
                func = dec.func
                if isinstance(func, ast.Name) and func.id in ('dataclass', 'preserve_typing'):
                    return True
                if isinstance(func, ast.Attribute) and func.attr in ('dataclass', 'preserve_typing'):
                    return True

    if hasattr(node, 'bases'):
        for base in node.bases:
            base_name = None
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if base_name in ('BaseModel', 'NamedTuple', 'TypedDict'):
                return True
    return False

def is_special_annotation(node):
    if isinstance(node, ast.Name) and node.id in ('ClassVar', 'Annotated'):
        return True
    if isinstance(node, ast.Attribute) and node.attr in ('ClassVar', 'Annotated'):
        return True
    if isinstance(node, ast.Subscript):
        return is_special_annotation(node.value)
    return False

class RemoveExplicitFields(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def visit_ClassDef(self, node):
        node.bases = [self.visit(b) for b in node.bases]
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]

        # Process class body
        if should_skip_class_fields(node):
            # Just process normal body recursively but keep AnnAssign
            node.body = self.suite(node.body, parent=node)
        else:
            new_body = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and stmt.value is None:
                    if not is_special_annotation(stmt.annotation):
                        # Remove it!
                        continue
                visited = self.visit(stmt)
                if isinstance(visited, list):
                    new_body.extend(visited)
                elif visited is not None:
                    new_body.append(visited)
            node.body = new_body

        if not node.body:
            node.body = [self.add_child(ast.Pass(), parent=node)]

        return node
