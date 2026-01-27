import python_minifier.ast as ast

from python_minifier.transforms.suite_transformer import SuiteTransformer
from python_minifier.util import is_constant_node


class RemoveEnvironmentChecks(SuiteTransformer):
    """
    Remove code guarded by static environment checks like TYPE_CHECKING or sys.version_info
    """

    def __init__(self, target_version):
        """
        :param target_version: Target python version tuple (e.g. (3, 12))
        """
        super(RemoveEnvironmentChecks, self).__init__()
        self.target_version = target_version
        self.type_checking_names = {"TYPE_CHECKING"}
        self.typing_module_names = {"typing"}
        self.version_info_names = {"version_info"}
        self.sys_module_names = {"sys"}

    def visit_Module(self, node):
        # Scan imports to find aliases
        self._scan_imports(node)
        return super().visit_Module(node)

    def _scan_imports(self, node):
        for stmt in node.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name == "typing":
                        self.typing_module_names.add(alias.asname or "typing")
                    elif alias.name == "sys":
                        self.sys_module_names.add(alias.asname or "sys")
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module == "typing":
                    for alias in stmt.names:
                        if alias.name == "TYPE_CHECKING":
                            self.type_checking_names.add(alias.asname or "TYPE_CHECKING")
                elif stmt.module == "sys":
                    for alias in stmt.names:
                        if alias.name == "version_info":
                            self.version_info_names.add(alias.asname or "version_info")

    def __call__(self, node):
        return self.visit(node)

    def _evaluate_version_check(self, node):
        """
        Evaluate a comparison against sys.version_info
        Returns True, False or None (if undecidable)
        """
        if not isinstance(node, ast.Compare):
            return None

        if len(node.ops) != 1 or len(node.comparators) != 1:
            return None

        # Check left side is sys.version_info
        left = node.left
        is_version_info = False

        # Case 1: sys.version_info (or alias.version_info)
        if isinstance(left, ast.Attribute):
            if (
                isinstance(left.value, ast.Name)
                and left.value.id in self.sys_module_names
                and left.attr == "version_info"
            ):
                is_version_info = True

        # Case 2: version_info (imported or aliased)
        elif isinstance(left, ast.Name) and left.id in self.version_info_names:
            is_version_info = True

        if not is_version_info:
            return None

        # Evaluate comparator
        comparator = node.comparators[0]
        try:
            # We need to extract the tuple value from the AST
            if isinstance(comparator, ast.Tuple):
                # Extract literal values from Tuple
                version_tuple = []
                for elt in comparator.elts:
                    if is_constant_node(elt, ast.Num):
                        version_tuple.append(elt.n)
                    else:
                        return None
                check_version = tuple(version_tuple)
            else:
                return None
        except Exception:
            return None

        op = node.ops[0]

        if isinstance(op, ast.Gt):
            return self.target_version > check_version
        elif isinstance(op, ast.GtE):
            return self.target_version >= check_version
        elif isinstance(op, ast.Lt):
            return self.target_version < check_version
        elif isinstance(op, ast.LtE):
            return self.target_version <= check_version
        elif isinstance(op, ast.Eq):
            return self.target_version == check_version
        elif isinstance(op, ast.NotEq):
            return self.target_version != check_version

        return None

    def _is_type_checking(self, node):
        """
        Check if node is TYPE_CHECKING
        """
        # Case 1: TYPE_CHECKING (or alias)
        if isinstance(node, ast.Name) and node.id in self.type_checking_names:
            return True

        # Case 2: typing.TYPE_CHECKING (or alias.TYPE_CHECKING)
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in self.typing_module_names
                and node.attr == "TYPE_CHECKING"
            ):
                return True

        return False

    def _is_not_type_checking(self, node):
        """
        Check if node is 'not TYPE_CHECKING'
        """
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return self._is_type_checking(node.operand)
        return False

    def visit_If(self, node):
        # 1. TYPE_CHECKING
        if self._is_type_checking(node.test):
            # if TYPE_CHECKING: ... -> Remove body, keep orelse
            if node.orelse:
                # Return the processed orelse block.
                # Since suite returns a list of nodes, this fits SuiteTransformer expectations.
                return self.suite(node.orelse, parent=ast.get_parent(node))
            else:
                # Remove the If node entirely
                return None

        # 2. not TYPE_CHECKING
        if self._is_not_type_checking(node.test):
            # if not TYPE_CHECKING: ... -> Keep body, remove orelse
            return self.suite(node.body, parent=ast.get_parent(node))

        # 3. sys.version_info
        version_result = self._evaluate_version_check(node.test)

        if version_result is True:
            # Condition is True: Keep body
            return self.suite(node.body, parent=ast.get_parent(node))
        elif version_result is False:
            # Condition is False: Keep orelse
            if node.orelse:
                return self.suite(node.orelse, parent=ast.get_parent(node))
            else:
                return None

        # 4. Undecidable: Recurse into children
        node.test = self.visit(node.test)
        node.body = self.suite(node.body, parent=node)
        if node.orelse:
            node.orelse = self.suite(node.orelse, parent=node)

        return node

    def suite(self, node_list, parent):
        """
        Process a list of statements, flattening any lists returned by visitors.
        """
        new_nodes = []
        for node in node_list:
            visited = self.visit(node)
            if visited is None:
                continue
            elif isinstance(visited, list):
                # Flatten list results (e.g. from visit_If lifting a block)
                new_nodes.extend(visited)
            else:
                new_nodes.append(visited)
        return new_nodes
