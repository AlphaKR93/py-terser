import python_minifier._ast as ast
from python_minifier._ast.annotation import get_parent
from python_minifier.transforms.suite_transformer import SuiteTransformer

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
    if isinstance(node, (ast.Constant, ast.Str)) and isinstance(getattr(node, 'value', getattr(node, 's', None)), str):
        return True
    return False

def has_preserve_typing(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    for dec in node.decorator_list:
        func = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(func, ast.Name) and func.id == 'preserve_typing':
            return True
        if isinstance(func, ast.Attribute) and func.attr == 'preserve_typing':
            return True
    return False

def has_no_type_check(node):
    if not hasattr(node, 'decorator_list') or not node.decorator_list:
        return False
    for dec in node.decorator_list:
        func = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(func, ast.Name) and func.id in ('no_type_check', 'no_type_check_decorator'):
            return True
        if isinstance(func, ast.Attribute) and func.attr in ('no_type_check', 'no_type_check_decorator'):
            return True
    return False

class RemoveAnnotations(SuiteTransformer):
    def __init__(self, options=None):
        super().__init__()
        if options is None:
            from python_minifier.transforms.remove_annotations_options import RemoveAnnotationsOptions
            self.options = RemoveAnnotationsOptions()
        elif isinstance(options, bool):
            from python_minifier.transforms.remove_annotations_options import RemoveAnnotationsOptions
            self.options = RemoveAnnotationsOptions(
                remove_variable_annotations=options,
                remove_return_annotations=options,
                remove_argument_annotations=options,
                remove_class_attribute_annotations=options
            )
        else:
            self.options = options
        self.basemodels = set()
        self._preserve_typing_stack = [False]
        self._no_type_check_stack = [False]

    def __call__(self, node):
        self.basemodels = get_basemodel_classes(node)
        return self.visit(node)

    def is_preserving_typing(self):
        return any(self._preserve_typing_stack)

    def is_no_type_check(self):
        return any(self._no_type_check_stack)

    def visit_ClassDef(self, node):
        is_bm_or_dc = (node.name in self.basemodels or is_dataclass(node))
        if is_bm_or_dc and has_no_type_check(node):
            raise RuntimeError(f"no_type_check decorator is not allowed on BaseModel or dataclass '{node.name}'.")

        self._preserve_typing_stack.append(has_preserve_typing(node))
        self._no_type_check_stack.append(has_no_type_check(node))

        node.bases = [self.visit(b) for b in node.bases]
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]

        node.body = self.suite(node.body, parent=node)

        self._preserve_typing_stack.pop()
        self._no_type_check_stack.pop()
        return node

    def visit_FunctionDef(self, node):
        self._preserve_typing_stack.append(has_preserve_typing(node))
        self._no_type_check_stack.append(has_no_type_check(node))

        remove_all = self.is_no_type_check()
        preserve = self.is_preserving_typing() and not remove_all

        # 1. Return annotations
        if hasattr(node, 'returns') and node.returns is not None:
            if is_literal_annotation(node.returns):
                if remove_all or self.options.remove_return_annotations:
                    node.returns = None
            elif remove_all or (self.options.remove_return_annotations and not preserve):
                if not contains_annotated(node.returns):
                    node.returns = None

        # 2. Argument annotations
        node.args = self._visit_arguments(node.args, remove_all or (self.options.remove_argument_annotations and not preserve))

        # 3. Body
        node.body = self.suite(node.body, parent=node)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        if hasattr(node, 'type_params') and node.type_params is not None:
            node.type_params = [self.visit(t) for t in node.type_params]

        self._preserve_typing_stack.pop()
        self._no_type_check_stack.pop()
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def _visit_arguments(self, node, remove):
        for arg_node in node.args + getattr(node, 'posonlyargs', []) + getattr(node, 'kwonlyargs', []):
            if arg_node.annotation:
                if is_literal_annotation(arg_node.annotation):
                    if remove or self.options.remove_argument_annotations:
                        arg_node.annotation = None
                elif remove:
                    if not contains_annotated(arg_node.annotation):
                        arg_node.annotation = None

        for attr in ('varargannotation', 'kwargannotation'):
            val = getattr(node, attr, None)
            if val:
                if is_literal_annotation(val):
                    if remove or self.options.remove_argument_annotations:
                        setattr(node, attr, None)
                elif remove:
                    if not contains_annotated(val):
                        setattr(node, attr, None)

        if node.vararg and getattr(node.vararg, 'annotation', None):
            val = node.vararg.annotation
            if is_literal_annotation(val):
                if remove or self.options.remove_argument_annotations:
                    node.vararg.annotation = None
            elif remove:
                if not contains_annotated(val):
                    node.vararg.annotation = None

        if node.kwarg and getattr(node.kwarg, 'annotation', None):
            val = node.kwarg.annotation
            if is_literal_annotation(val):
                if remove or self.options.remove_argument_annotations:
                    node.kwarg.annotation = None
            elif remove:
                if not contains_annotated(val):
                    node.kwarg.annotation = None

        return node

    def visit_AnnAssign(self, node):
        parent = get_parent(node)
        remove_all = self.is_no_type_check()
        preserve = self.is_preserving_typing() and not remove_all

        # 1. String-literal annotation check
        if is_literal_annotation(node.annotation):
            if isinstance(parent, ast.ClassDef):
                is_bm_or_dc = (parent.name in self.basemodels or is_dataclass(parent))
                if is_bm_or_dc:
                    raise RuntimeError(f"String literal annotation '{node.annotation}' is not allowed on BaseModel or dataclass field '{node.target.id}'")
            is_class_attr = isinstance(parent, ast.ClassDef)
            should_remove = False
            if is_class_attr:
                should_remove = remove_all or self.options.remove_class_attribute_annotations
            else:
                should_remove = remove_all or self.options.remove_variable_annotations
            if should_remove:
                if node.value:
                    return self.add_child(ast.Assign(targets=[node.target], value=node.value), parent=parent)
                return None
            return node

        # 2. Skip if contains Annotated
        if contains_annotated(node.annotation) and not remove_all:
            return node

        # 3. Field-level skip check (BaseModel / dataclass / NamedTuple / TypedDict)
        if isinstance(parent, ast.ClassDef):
            is_preserved = (parent.name in self.basemodels or is_dataclass(parent) or is_typing_sensitive(parent))
            if is_preserved and not remove_all:
                if is_typing_sensitive(parent):
                    node.annotation = self.add_child(ast.Constant(value=None), parent=parent)
                return node

        # 4. Normal removal
        is_class_attr = isinstance(parent, ast.ClassDef)
        if is_class_attr:
            enabled = self.options.remove_class_attribute_annotations
        else:
            enabled = self.options.remove_variable_annotations

        if (remove_all or enabled) and not preserve:
            if node.value:
                return self.add_child(ast.Assign(targets=[node.target], value=node.value), parent=parent)
            else:
                node.annotation = self.add_child(ast.Num(0), parent=parent)
                return node

        return node

    def suite(self, node_list, parent):
        declared = set()
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = parent.args
            for arg_node in args.args + getattr(args, 'posonlyargs', []) + getattr(args, 'kwonlyargs', []):
                declared.add(arg_node.arg)
            if args.vararg:
                declared.add(args.vararg.arg if hasattr(args.vararg, 'arg') else args.vararg)
            if args.kwarg:
                declared.add(args.kwarg.arg if hasattr(args.kwarg, 'arg') else args.kwarg)

        clean_nodes = []
        for n in node_list:
            if n is None:
                continue

            if isinstance(n, ast.AnnAssign) and n.value is None and isinstance(n.target, ast.Name):
                if n.target.id in declared:
                    continue

            visited = self.visit(n)

            stmt = visited if not isinstance(visited, list) else (visited[0] if visited else None)
            if stmt:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        for sub in ast.walk(target):
                            if isinstance(sub, ast.Name):
                                declared.add(sub.id)
                elif isinstance(stmt, ast.AnnAssign):
                    if stmt.value is not None and isinstance(stmt.target, ast.Name):
                        declared.add(stmt.target.id)
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    declared.add(stmt.name)

            if isinstance(visited, list):
                clean_nodes.extend(visited)
            elif visited is not None:
                clean_nodes.append(visited)
        return clean_nodes
