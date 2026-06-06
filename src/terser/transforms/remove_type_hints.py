import terser.ast_compat as ast
from terser.ast_annotation import get_parent
from terser.transforms.remove_annotations_options import RemoveAnnotationsOptions
from terser.transforms.suite_transformer import SuiteTransformer
from terser.transforms.remove_annotations import contains_annotated, is_literal_annotation

class RemoveTypeHints(SuiteTransformer):
    """
    Remove type hints from functions, arguments, and local variables.
    """

    def __init__(self, options):
        assert isinstance(options, RemoveAnnotationsOptions)
        self._options = options
        super(RemoveTypeHints, self).__init__()

    def __call__(self, node):
        return self.visit(node)

    def visit_FunctionDef(self, node):
        node.args = self.visit_arguments(node.args)
        node.body = self.suite(node.body, parent=node)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]

        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]

        if hasattr(node, 'returns') and node.returns is not None:
            if self._options.remove_return_annotations:
                # If return annotation is literal type, always remove it
                if is_literal_annotation(node.returns):
                    node.returns = None
                # Otherwise, only keep if it contains Annotated
                elif not contains_annotated(node.returns):
                    node.returns = None

        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_arguments(self, node):
        assert isinstance(node, ast.arguments)

        if hasattr(node, 'posonlyargs') and node.posonlyargs:
            node.posonlyargs = [self.visit_arg(a) for a in node.posonlyargs]

        if node.args:
            node.args = [self.visit_arg(a) for a in node.args]

        if hasattr(node, 'kwonlyargs') and node.kwonlyargs:
            node.kwonlyargs = [self.visit_arg(a) for a in node.kwonlyargs]

        if hasattr(node, 'varargannotation'):
            if self._options.remove_argument_annotations and node.varargannotation:
                if not contains_annotated(node.varargannotation):
                    node.varargannotation = None
        else:
            if node.vararg:
                node.vararg = self.visit_arg(node.vararg)

        if hasattr(node, 'kwargannotation'):
            if self._options.remove_argument_annotations and node.kwargannotation:
                if not contains_annotated(node.kwargannotation):
                    node.kwargannotation = None
        else:
            if node.kwarg:
                node.kwarg = self.visit_arg(node.kwarg)

        return node

    def visit_arg(self, node):
        if self._options.remove_argument_annotations and node.annotation:
            if not contains_annotated(node.annotation):
                node.annotation = None
        return node

    def visit_AnnAssign(self, node):
        parent = get_parent(node)
        if isinstance(parent, ast.ClassDef):
            # Handled by RemoveAnnotations
            return node

        if not self._options.remove_variable_annotations:
            return node

        # If it contains Annotated, we keep it
        if contains_annotated(node.annotation):
            return node

        # Otherwise, remove the annotation
        if node.value:
            return self.add_child(ast.Assign([node.target], node.value), parent=parent, namespace=node.namespace)
        else:
            # Valueless annotation is set to 0 to keep the variable local
            node.annotation = self.add_child(ast.Num(0), parent=parent, namespace=node.namespace)
            return node
