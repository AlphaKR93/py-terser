import python_minifier.ast as ast

from python_minifier.transforms.remove_annotations_options import RemoveAnnotationsOptions
from python_minifier.transforms.suite_transformer import SuiteTransformer


class RemoveAnnotations(SuiteTransformer):
    """
    Remove or simplify type annotations from source to reduce code size.
    """

    def __init__(self, options: RemoveAnnotationsOptions):
        self._options = options
        super(RemoveAnnotations, self).__init__()

    def __call__(self, node):
        return self.visit(node)

    def _is_runtime_annotation(self, node):
        """Check if an annotation is likely used at runtime (e.g., Annotated, Query)."""
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "Annotated":
                return True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "Annotated" in node.value:
                return True
        elif isinstance(node, ast.Call):
            return True
        return False

    def visit_FunctionDef(self, node):
        node.args = self.visit_arguments(node.args)
        node.body = self.suite(node.body, parent=node)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]

        if hasattr(node, "type_params"):
            node.type_params = []

        if hasattr(node, "returns") and node.returns is not None:
            if self._options.remove_return_annotations:
                node.returns = None
            elif not self._is_runtime_annotation(node.returns):
                node.returns = None

        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_arguments(self, node):
        assert isinstance(node, ast.arguments)

        if hasattr(node, "posonlyargs"):
            node.posonlyargs = [self.visit_arg(a) for a in node.posonlyargs]
        if node.args:
            node.args = [self.visit_arg(a) for a in node.args]
        if hasattr(node, "kwonlyargs"):
            node.kwonlyargs = [self.visit_arg(a) for a in node.kwonlyargs]

        if node.vararg and hasattr(node.vararg, "annotation"):
            self.visit_arg(node.vararg)
        if node.kwarg and hasattr(node.kwarg, "annotation"):
            self.visit_arg(node.kwarg)

        return node

    def visit_arg(self, node):
        if not hasattr(node, "annotation") or node.annotation is None:
            return node

        if node.annotation is None:
            return node

        if self._options.remove_argument_annotations:
            # If True, remove ALL annotations, no exceptions.
            node.annotation = None
        else:
            # If False, preserve runtime types but remove string literals (Forward refs)
            # unless they look like runtime annotations (e.g. "Annotated[...]")
            if isinstance(node.annotation, ast.Constant) and not self._is_runtime_annotation(node.annotation):
                node.annotation = None

        return node

    def visit_AnnAssign(self, node):
        parent = ast.get_parent(node)
        is_class_attribute = isinstance(parent, ast.ClassDef)

        if not is_class_attribute:
            # Handle local variables
            if self._options.remove_variable_annotations:
                if node.value:
                    return self.add_child(
                        ast.Assign(targets=[node.target], value=node.value), parent=parent, namespace=node.namespace
                    )
                else:
                    return self.add_child(ast.Pass(), parent=parent, namespace=node.namespace)
            else:
                return self.generic_visit(node)

        # From here, we are handling class attributes only.

        # Preserve runtime-critical annotations
        if self._is_runtime_annotation(node.annotation):
            return self.generic_visit(node)

        # Determine if this annotation should be processed
        should_process = False
        is_string_annotation = isinstance(node.annotation, ast.Constant) and isinstance(node.annotation.value, str)

        if is_string_annotation:
            # Rule: String annotations are always candidates for processing.
            should_process = True
            try:
                ann_ast = ast.parse(node.annotation.value, mode="eval").body
                simplified_node = None
                if isinstance(ann_ast, ast.Subscript):
                    simplified_node = ann_ast.value
                elif isinstance(ann_ast, ast.Name):
                    simplified_node = ann_ast

                if simplified_node:
                    node.annotation = self.add_child(simplified_node, parent=node, namespace=node.namespace)
            except (SyntaxError, ValueError):
                pass
        elif self._options.remove_class_attribute_annotations:
            # Non-string annotations are processed only if the option is enabled.
            should_process = True

        if should_process:
            # Aggressive removal: if enabled and the attribute has no value, replace annotation with 0.
            if self._options.aggressively_minify_class_attributes and node.value is None:
                node.annotation = self.add_child(ast.Constant(value=0), parent=node, namespace=node.namespace)
                return self.generic_visit(node)

            # Standard simplification for subscripted types if not aggressively removed.
            if isinstance(node.annotation, ast.Subscript):
                node.annotation = self.add_child(node.annotation.value, parent=node, namespace=node.namespace)

        # Keep the node and its (possibly modified) annotation.
        return self.generic_visit(node)
