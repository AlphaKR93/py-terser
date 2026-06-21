import terser._ast as ast
from terser.transforms.suite_transformer import SuiteTransformer

def targets_equal(t1, t2):
    if type(t1) != type(t2):
        return False
    if isinstance(t1, ast.Name):
        return t1.id == t2.id
    if isinstance(t1, ast.Attribute):
        return t1.attr == t2.attr and targets_equal(t1.value, t2.value)
    return False

def get_assignment_info(stmt):
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        return stmt.targets[0], '=', stmt.value
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        return stmt.target, '=', stmt.value
    if isinstance(stmt, ast.AugAssign):
        return stmt.target, type(stmt.op), stmt.value
    return None

def rebuild_assignment(target, op, expr, parent, add_child):
    if op == '=':
        return add_child(ast.Assign(targets=[target], value=expr), parent=parent)
    else:
        return add_child(ast.AugAssign(target=target, op=op(), value=expr), parent=parent)

def get_recursive_assignment(node):
    # Returns (target, op, expr) if node is an If statement representing an assignment ternary chain
    if not isinstance(node, ast.If):
        return None
    if len(node.body) != 1:
        return None
    info = get_assignment_info(node.body[0])
    if not info:
        return None
    target, op, value = info

    if not node.orelse:
        return None

    if len(node.orelse) == 1:
        else_stmt = node.orelse[0]
        if isinstance(else_stmt, ast.If):
            sub = get_recursive_assignment(else_stmt)
            if sub:
                sub_target, sub_op, sub_expr = sub
                if targets_equal(target, sub_target) and op == sub_op:
                    return target, op, ast.IfExp(test=node.test, body=value, orelse=sub_expr)
        else:
            else_info = get_assignment_info(else_stmt)
            if else_info:
                else_target, else_op, else_value = else_info
                if targets_equal(target, else_target) and op == else_op:
                    return target, op, ast.IfExp(test=node.test, body=value, orelse=else_value)
    return None

class ConvertToTernary(SuiteTransformer):
    def __call__(self, node):
        return self.visit(node)

    def suite(self, node_list, parent):
        visited_list = []
        for node in node_list:
            visited = self.visit(node)
            if visited is not None:
                if isinstance(visited, list):
                    visited_list.extend(visited)
                else:
                    visited_list.append(visited)

        i = 0
        while i < len(visited_list):
            node = visited_list[i]

            # Case 1: Return with explicit else
            if isinstance(node, ast.If) and len(node.body) == 1 and len(node.orelse) == 1:
                stmt_body = node.body[0]
                stmt_else = node.orelse[0]
                if isinstance(stmt_body, ast.Return) and isinstance(stmt_else, ast.Return):
                    a = stmt_body.value or self.add_child(ast.Constant(value=None), parent=parent)
                    b = stmt_else.value or self.add_child(ast.Constant(value=None), parent=parent)
                    ternary = self.add_child(ast.IfExp(test=node.test, body=a, orelse=b), parent=parent)
                    new_return = self.add_child(ast.Return(value=ternary), parent=parent)
                    visited_list[i] = new_return
                    node = new_return

            # Case 3: Assignment with explicit else (and elif chain)
            if isinstance(node, ast.If) and node.orelse:
                chain = get_recursive_assignment(node)
                if chain:
                    target, op, expr = chain
                    new_assign = rebuild_assignment(target, op, expr, parent, self.add_child)
                    visited_list[i] = new_assign
                    node = new_assign

            # Implicit else cases (needs next statement)
            if i + 1 < len(visited_list):
                next_node = visited_list[i + 1]

                # Case 2: Return with implicit else
                if isinstance(node, ast.If) and not node.orelse and len(node.body) == 1:
                    stmt_body = node.body[0]
                    if isinstance(stmt_body, ast.Return) and isinstance(next_node, ast.Return):
                        a = stmt_body.value or self.add_child(ast.Constant(value=None), parent=parent)
                        b = next_node.value or self.add_child(ast.Constant(value=None), parent=parent)
                        ternary = self.add_child(ast.IfExp(test=node.test, body=a, orelse=b), parent=parent)
                        new_return = self.add_child(ast.Return(value=ternary), parent=parent)
                        visited_list[i] = new_return
                        visited_list.pop(i + 1)
                        continue

                # Case 4: Assignment with implicit else
                if isinstance(node, ast.If) and not node.orelse and len(node.body) == 1:
                    info_body = get_assignment_info(node.body[0])
                    info_next = get_assignment_info(next_node)
                    if info_body and info_next:
                        t1, op1, v1 = info_body
                        t2, op2, v2 = info_next
                        if targets_equal(t1, t2) and op1 == op2:
                            ternary = self.add_child(ast.IfExp(test=node.test, body=v1, orelse=v2), parent=parent)
                            new_assign = rebuild_assignment(t1, op1, ternary, parent, self.add_child)
                            visited_list[i] = new_assign
                            visited_list.pop(i + 1)
                            continue

            i += 1
        return visited_list
