import terser.ast_compat as ast
from terser.ast_annotation import get_parent
from terser.transforms.remove_annotations_options import RemoveAnnotationsOptions
from terser.transforms.suite_transformer import SuiteTransformer

def contains_annotated(node):
    if isinstance(node, ast.Name):
        return node.id == 'Annotated'
    if isinstance(node, ast.Attribute):
        return node.attr == 'Annotated'
    for child in ast.iter_child_nodes(node):
        if contains_annotated(child):
            return True
    return False

def get_basemodel_classes(module):
    basemodels = {'BaseModel'}
    while True:
        added = False
        for node in ast.walk(module):
            if isinstance(node, ast.ClassDef):
                if node.name in basemodels:
                    continue
                for base in node.bases:
                    base_name = None
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name in basemodels:
                        basemodels.add(node.name)
                        added = True
                        break
        if not added:
            break
    return basemodels

def is_dataclass(class_def):
    if not hasattr(class_def, 'decorator_list') or not class_def.decorator_list:
        return False
    for dec in class_def.decorator_list:
        func = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(func, ast.Name) and func.id == 'dataclass':
            return True
        if isinstance(func, ast.Attribute) and func.attr == 'dataclass':
            return True
    return False

def is_typing_sensitive(class_def):
    if len(class_def.bases) == 0:
        return False
    tricky_types = ['NamedTuple', 'TypedDict']
    for base_node in class_def.bases:
        if isinstance(base_node, ast.Name) and base_node.id in tricky_types:
            return True
        elif isinstance(base_node, ast.Attribute) and base_node.attr in tricky_types:
            return True
    return False

def is_literal_annotation(node):
    # e.g., x: "int"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.Str):
        return True
    return False

class RemoveAnnotations(SuiteTransformer):
    """
    Remove type annotations from class attributes/fields, keeping BaseModel, dataclass, and Annotated.
    """

    def __init__(self, options):
        assert isinstance(options, RemoveAnnotationsOptions)
        self._options = options
        super(RemoveAnnotations, self).__init__()

    def __call__(self, node):
        self.basemodels = get_basemodel_classes(node)
        return self.visit(node)

    def visit_ClassDef(self, node):
        # Only process inside ClassDef body
        self.in_preserved_class = (
            node.name in self.basemodels or
            is_dataclass(node) or
            is_typing_sensitive(node)
        )
        
        # Traverse bases, decorators, type_params first
        node.bases = [self.visit(b) for b in node.bases]
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]

        # Visit class body
        node.body = self.suite(node.body, parent=node)
        return node

    def visit_AnnAssign(self, node):
        parent = get_parent(node)
        if not isinstance(parent, ast.ClassDef):
            # Handled by RemoveTypeHints
            return node

        if not self._options.remove_class_attribute_annotations:
            return node

        # If annotation is literal type (e.g. x: "Foo"), we always remove it
        if is_literal_annotation(node.annotation):
            if node.value:
                return self.add_child(ast.Assign([node.target], node.value), parent=parent, namespace=node.namespace)
            else:
                return None

        # Keep annotation if in BaseModel, dataclass, NamedTuple, TypedDict, or contains Annotated
        if self.in_preserved_class or contains_annotated(node.annotation):
            return node

        # Otherwise, remove the annotation
        if node.value:
            return self.add_child(ast.Assign([node.target], node.value), parent=parent, namespace=node.namespace)
        else:
            # Empty annotation is set to 0 to keep the variable local
            node.annotation = self.add_child(ast.Num(0), parent=parent, namespace=node.namespace)
            return node
