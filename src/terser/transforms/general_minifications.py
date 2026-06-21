import terser._ast as ast
from terser._ast.annotation import get_parent
from terser.transforms.suite_transformer import SuiteTransformer
from terser.transforms.constant_folding import unparse_expression

def is_side_effect_free(node):
    if isinstance(node, (ast.Num, ast.Str, ast.Bytes, ast.NameConstant, ast.Constant, ast.Ellipsis)):
        return True
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(is_side_effect_free(x) for x in node.elts)
    if isinstance(node, ast.Dict):
        return all(is_side_effect_free(k) if k is not None else True for k in node.keys) and all(is_side_effect_free(v) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        return is_side_effect_free(node.operand)
    if isinstance(node, ast.BinOp):
        return is_side_effect_free(node.left) and is_side_effect_free(node.right)
    return False

def is_equal_constant(v1, v2):
    if isinstance(v1, ast.NameConstant) and isinstance(v2, ast.NameConstant):
        return v1.value == v2.value
    if isinstance(v1, ast.Num) and isinstance(v2, ast.Num):
        return v1.n == v2.n
    if isinstance(v1, ast.Constant) and isinstance(v2, ast.Constant):
        return v1.value == v2.value
    return False

def is_propagate_constant(node):
    if isinstance(node, (ast.Num, ast.NameConstant, ast.Constant)):
        try:
            val_repr = unparse_expression(node)
            return len(val_repr) <= 10
        except Exception:
            return False
    if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) == 0:
        return True
    if isinstance(node, ast.Dict) and len(node.keys) == 0:
        return True
    return False

class ScopeAnalyzer(object):
    def __init__(self, scope_node):
        self.scope_node = scope_node
        self.reads = {}  # var_name -> count
        self.writes = {} # var_name -> count
        self.assign_nodes = {} # var_name -> list of Assign nodes
        self.global_names = set()
        self.nonlocal_names = set()
        self.analyze()

    def analyze(self):
        # Scan immediate scope (excluding nested function/class contents for writes, but count references)
        class Visitor(ast.NodeVisitor):
            def __init__(self, analyzer):
                self.analyzer = analyzer
                self.in_nested = 0

            def visit_Global(self, node):
                for name in node.names:
                    self.analyzer.global_names.add(name)

            def visit_Nonlocal(self, node):
                for name in node.names:
                    self.analyzer.nonlocal_names.add(name)

            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load):
                    self.analyzer.reads[node.id] = self.analyzer.reads.get(node.id, 0) + 1
                elif isinstance(node.ctx, ast.Store):
                    if self.in_nested == 0:
                        self.analyzer.writes[node.id] = self.analyzer.writes.get(node.id, 0) + 1

            def visit_Assign(self, node):
                if self.in_nested == 0:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.analyzer.assign_nodes.setdefault(target.id, []).append(node)
                self.generic_visit(node)

            def visit_FunctionDef(self, node):
                # count function name as write in current scope
                if self.in_nested == 0:
                    self.analyzer.writes[node.name] = self.analyzer.writes.get(node.name, 0) + 1
                self.in_nested += 1
                self.generic_visit(node)
                self.in_nested -= 1

            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)

            def visit_ClassDef(self, node):
                if self.in_nested == 0:
                    self.analyzer.writes[node.name] = self.analyzer.writes.get(node.name, 0) + 1
                self.in_nested += 1
                self.generic_visit(node)
                self.in_nested -= 1

        visitor = Visitor(self)
        for child in ast.iter_child_nodes(self.scope_node):
            visitor.visit(child)

class GeneralMinifications(SuiteTransformer):
    """
    Apply T19 (Dead Store Eliminator), T20 (Unused Exception Name Pruner), T21 (Chained Assignment Consolidation), and T22 (Local Constant Propagator).
    """
    def __call__(self, node):
        return self.visit(node)

    def visit_FunctionDef(self, node):
        # Run optimizations on local variables
        node.args = self.visit(node.args)
        if hasattr(node, 'returns') and node.returns is not None:
            node.returns = self.visit(node.returns)
        
        # Analyze local scope
        analyzer = ScopeAnalyzer(node)
        
        # Identify variables for dead store elimination and local constant propagation
        self.dead_stores = set()
        self.propagate_map = {} # name -> const_node
        self.pruned_assigns = set()

        for var, write_count in analyzer.writes.items():
            if var in analyzer.global_names or var in analyzer.nonlocal_names:
                continue
            
            read_count = analyzer.reads.get(var, 0)
            
            # T19: Dead Store
            if read_count == 0 or var == '_':
                self.dead_stores.add(var)
            
            # T22: Local Constant Propagation
            elif write_count == 1 and var in analyzer.assign_nodes:
                assign_node = analyzer.assign_nodes[var][0]
                if is_propagate_constant(assign_node.value):
                    const = assign_node.value
                    try:
                        const_repr = unparse_expression(const)
                        # savings formula: read_count * (len(const_repr) - len(var)) - (len(var) + 3 + len(const_repr) + 1) < 0
                        cost_diff = read_count * (len(const_repr) - len(var)) - (len(var) + 4 + len(const_repr))
                        if cost_diff < 0:
                            self.propagate_map[var] = const
                            self.pruned_assigns.add(assign_node)
                    except Exception:
                        pass

        # Visit body with these maps
        node.body = self.suite(node.body, parent=node)
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_Name(self, node):
        # Apply local constant propagation (T22)
        if isinstance(node.ctx, ast.Load) and hasattr(self, 'propagate_map') and node.id in self.propagate_map:
            from terser.transforms.inline_functions import clean_copy_node
            return clean_copy_node(self.propagate_map[node.id])
        return node

    def visit_Assign(self, node):
        node = self.generic_visit(node)
        # Check if it was pruned by constant propagation
        if hasattr(self, 'pruned_assigns') and node in self.pruned_assigns:
            return None

        # Apply Dead Store Eliminator (T19)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            # check if dead store
            is_dead = False
            if var_name == '_':
                is_dead = True
            elif hasattr(self, 'dead_stores') and var_name in self.dead_stores:
                is_dead = True
            
            if is_dead:
                if is_side_effect_free(node.value):
                    return None
                else:
                    parent = get_parent(node)
                    return self.add_child(ast.Expr(value=node.value), parent=parent, namespace=node.namespace)
        return node

    def visit_ExceptHandler(self, node):
        node = self.generic_visit(node)
        # Apply Unused Exception Name Pruner (T20)
        if node.name:
            # check if node.name is read in node.body
            reads_name = False
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id == node.name and isinstance(child.ctx, ast.Load):
                    reads_name = True
                    break
            if not reads_name:
                node.name = None
        return node

    def suite(self, node_list, parent):
        visited_list = []
        for node in node_list:
            visited = self.visit(node)
            if visited is not None:
                if isinstance(visited, list):
                    visited_list.extend(visited)
                else:
                    visited_list.append(visited)
        
        # Apply Chained Assignment Consolidation (T21)
        i = 0
        while i < len(visited_list):
            node = visited_list[i]
            if i + 1 < len(visited_list):
                next_node = visited_list[i + 1]
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if isinstance(next_node, ast.Assign) and len(next_node.targets) == 1 and isinstance(next_node.targets[0], ast.Name):
                        if is_equal_constant(node.value, next_node.value):
                            # combine targets
                            node.targets.append(next_node.targets[0])
                            visited_list.pop(i + 1)
                            continue
            i += 1
        return visited_list
