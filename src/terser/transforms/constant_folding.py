import math
import re
import unicodedata

import terser._ast as ast
from terser._ast.annotation import get_parent
from terser._ast.compare import compare_ast
from terser.printer.expression_printer import ExpressionPrinter
from terser.transforms.suite_transformer import SuiteTransformer
from terser.util import is_constant_node

def equal_value_and_type(a, b):
    if type(a) != type(b):
        return False

    if isinstance(a, float) and math.isnan(a) and not math.isnan(b):
        return False

    return a == b

def safe_eval(expression):
    empty_globals = {}
    empty_locals = {}
    return eval(expression, empty_globals, empty_locals)

def unparse_expression(node):
    expression_printer = ExpressionPrinter()
    return expression_printer(node)

def expand_unicode_escapes(s):
    # Match double backslashes or unicode escape sequences
    pattern = re.compile(r'\\{2}|\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})')
    def subst(match):
        if match.group(0) == '\\\\':
            return '\\\\'
        esc = match.group(0)
        val = int(esc[2:], 16)
        try:
            char = chr(val)
            # Do not expand control characters or line/paragraph separators
            if unicodedata.category(char)[0] not in ('C', 'Z'):
                return char
        except Exception:
            pass
        return esc
    return pattern.sub(subst, s)

class ConstantTransformer(SuiteTransformer):
    """
    Base ConstantTransformer visitor.
    """
    def __init__(self, options=None):
        super(ConstantTransformer, self).__init__()
        self.options = options or {}

class DebugConstantTransformer(ConstantTransformer):
    def visit_Name(self, node):
        if self.options.get('remove_debug', False):
            if node.id in ('__debug__', 'TYPE_CHECKING') and isinstance(getattr(node, 'ctx', None), ast.Load):
                return self.add_child(ast.NameConstant(value=False), parent=get_parent(node), namespace=node.namespace)
        return node

    def visit_Attribute(self, node):
        node.value = self.visit(node.value)
        if self.options.get('remove_debug', False):
            if node.attr == 'TYPE_CHECKING':
                is_typing = False
                if isinstance(node.value, ast.Name) and node.value.id == 'typing':
                    is_typing = True
                elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == '__import__':
                    if len(node.value.args) >= 1:
                        arg0 = node.value.args[0]
                        if isinstance(arg0, ast.Constant) and arg0.value == 'typing':
                            is_typing = True
                        elif isinstance(arg0, ast.Str) and arg0.s == 'typing':
                            is_typing = True
                if is_typing:
                    return self.add_child(ast.NameConstant(value=False), parent=get_parent(node), namespace=node.namespace)
        return node

def shortest_number_node(value, parent, namespace, add_child_fn):
    if isinstance(value, float):
        candidates = [repr(value)]
        for prec in range(1, 10):
            try:
                candidates.append("{:.{}e}".format(value, prec))
            except Exception:
                pass
        for prec in range(0, 10):
            try:
                candidates.append("{:.{}f}".format(value, prec))
            except Exception:
                pass
        valid_candidates = []
        for c in candidates:
            try:
                c_clean = c.replace('e+', 'e')
                if c_clean.startswith('0.'):
                    c_clean = c_clean[1:]
                elif c_clean.startswith('-0.'):
                    c_clean = '-' + c_clean[2:]
                val = eval(c_clean, {}, {})
                if type(val) == type(value) and val == value:
                    valid_candidates.append(c_clean)
            except Exception:
                pass
        if valid_candidates:
            best = min(valid_candidates, key=len)
            parsed = ast.parse(best, mode='eval').body
            return add_child_fn(parsed, parent, namespace)
    elif isinstance(value, int):
        candidates = [str(value), hex(value), oct(value), bin(value)]
        valid_candidates = []
        for c in candidates:
            try:
                val = eval(c, {}, {})
                if type(val) == type(value) and val == value:
                    valid_candidates.append(c)
            except Exception:
                pass
        if valid_candidates:
            best = min(valid_candidates, key=len)
            parsed = ast.parse(best, mode='eval').body
            return add_child_fn(parsed, parent, namespace)
    return None

class NumberRepresentationOptimizer(ConstantTransformer):
    def visit_Num(self, node):
        val = node.n
        parent = get_parent(node)
        if isinstance(val, (int, float)):
            is_neg = False
            if val < 0 or (isinstance(val, float) and repr(val).startswith('-')):
                is_neg = True
                val = -val
            opt = shortest_number_node(val, parent, node.namespace, self.add_child)
            if opt is not None:
                if is_neg:
                    return self.add_child(ast.UnaryOp(op=ast.USub(), operand=opt), parent=parent, namespace=node.namespace)
                return opt
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)):
            val = node.value
            parent = get_parent(node)
            is_neg = False
            if val < 0 or (isinstance(val, float) and repr(val).startswith('-')):
                is_neg = True
                val = -val
            opt = shortest_number_node(val, parent, node.namespace, self.add_child)
            if opt is not None:
                if is_neg:
                    return self.add_child(ast.UnaryOp(op=ast.USub(), operand=opt), parent=parent, namespace=node.namespace)
                return opt
        return node

class EnvironmentConstantTransformer(ConstantTransformer):
    def visit_Attribute(self, node):
        node.value = self.visit(node.value)
        if isinstance(node.value, ast.Name) and node.value.id == 'sys':
            version_info = self.options.get('version_info', (3, 12, 0))
            platform = self.options.get('platform', 'linux')
            if node.attr == 'version_info':
                elts = [self.add_child(ast.Num(n=x), parent=node, namespace=node.namespace) for x in version_info]
                return self.add_child(ast.Tuple(elts=elts, ctx=ast.Load()), parent=get_parent(node), namespace=node.namespace)
            elif node.attr == 'platform':
                return self.add_child(ast.Str(s=platform), parent=get_parent(node), namespace=node.namespace)
        return node

def is_foldable_constant(node):
    if is_constant_node(node, (ast.Num, ast.NameConstant)):
        return True
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, (ast.USub, ast.Invert)):
            return is_constant_node(node.operand, ast.Num)
    if isinstance(node, ast.Tuple):
        return all(is_foldable_constant(elt) for elt in node.elts)
    return False

def get_constant_value(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.NameConstant):
        return node.value
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub) and isinstance(node.operand, (ast.Num, ast.Constant)):
            val = node.operand.n if isinstance(node.operand, ast.Num) else node.operand.value
            return -val
        if isinstance(node.op, ast.Invert) and isinstance(node.operand, (ast.Num, ast.Constant)):
            val = node.operand.n if isinstance(node.operand, ast.Num) else node.operand.value
            return ~val
    if isinstance(node, ast.Tuple):
        return tuple(get_constant_value(elt) for elt in node.elts)
    raise ValueError("Not a foldable constant")

class ExpressionFolder(ConstantTransformer):
    def visit_BoolOp(self, node):
        node.values = [self.visit(val) for val in node.values]
        is_and = isinstance(node.op, ast.And)

        # 1. Eliminate redundant leading values
        simplified_values = []
        for i, val in enumerate(node.values):
            if i < len(node.values) - 1 and is_foldable_constant(val):
                try:
                    const_val = get_constant_value(val)
                    if is_and and const_val:
                        # True and X -> X
                        continue
                    elif not is_and and not const_val:
                        # False or X -> X
                        continue
                except ValueError:
                    pass
            simplified_values.append(val)
        node.values = simplified_values

        # 2. Apply short-circuiting
        shorter_values = []
        for val in node.values:
            shorter_values.append(val)
            if is_foldable_constant(val):
                try:
                    const_val = get_constant_value(val)
                    if is_and and not const_val:
                        # False and X -> False
                        break
                    elif not is_and and const_val:
                        # True or X -> True
                        break
                except ValueError:
                    pass
        node.values = shorter_values

        if len(node.values) == 1:
            return node.values[0]

        if all(is_foldable_constant(val) for val in node.values):
            return self.fold(node)

        return node

    def visit_Compare(self, node):
        node.left = self.visit(node.left)
        node.comparators = [self.visit(c) for c in node.comparators]

        if not is_foldable_constant(node.left):
            return node
        if not all(is_foldable_constant(c) for c in node.comparators):
            return node

        return self.fold(node)

    def fold(self, node):
        try:
            original_expression = unparse_expression(node)
            original_value = safe_eval(original_expression)
        except Exception:
            return node

        if isinstance(original_value, float) and math.isnan(original_value):
            return node
        elif isinstance(original_value, bool):
            new_node = ast.NameConstant(value=original_value)
        elif isinstance(original_value, (int, float, complex)):
            try:
                if repr(original_value).startswith('-'):
                    new_node = ast.UnaryOp(op=ast.USub(), operand=ast.Num(n=-original_value))
                else:
                    new_node = ast.Num(n=original_value)
            except Exception:
                return node
        else:
            return node

        try:
            folded_expression = unparse_expression(new_node)
            folded_value = safe_eval(folded_expression)
        except Exception:
            return node

        if len(folded_expression) >= len(original_expression):
            return node

        try:
            folded_ast = ast.parse(folded_expression, 'folded expression', mode='eval')
            compare_ast(new_node, folded_ast.body)
        except Exception:
            return node

        if not equal_value_and_type(folded_value, original_value):
            return node

        return self.add_child(new_node, get_parent(node), node.namespace)

    def visit_BinOp(self, node):
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)

        if not is_foldable_constant(node.left):
            return node
        if not is_foldable_constant(node.right):
            return node

        if isinstance(node.op, (ast.Pow, ast.Div, ast.MatMult)):
            return node

        return self.fold(node)

    def visit_UnaryOp(self, node):
        node.operand = self.visit(node.operand)

        if not is_foldable_constant(node.operand):
            return node

        if not isinstance(node.op, (ast.USub, ast.UAdd, ast.Invert, ast.Not)):
            return node

        return self.fold(node)

def get_shortest_literal(val):
    if isinstance(val, str):
        candidates = []
        candidates.append(repr(val))
        for q in ["'", '"']:
            try:
                parts = []
                for c in val:
                    if c == '\\':
                        parts.append('\\\\')
                    elif c == q:
                        parts.append('\\' + q)
                    elif c == '\n':
                        parts.append('\\n')
                    elif c == '\r':
                        parts.append('\\r')
                    elif c == '\t':
                        parts.append('\\t')
                    elif c.isprintable():
                        parts.append(c)
                    else:
                        o = ord(c)
                        if o < 256:
                            parts.append('\\x{:02x}'.format(o))
                        elif o < 65536:
                            parts.append('\\u{:04x}'.format(o))
                        else:
                            parts.append('\\U{:08x}'.format(o))
                candidates.append(q + ''.join(parts) + q)
            except Exception:
                pass
        for q in ["'", '"']:
            if val and val[-1] == '\\':
                continue
            if q in val:
                continue
            if any(not (c.isprintable() or c == ' ') for c in val):
                continue
            candidates.append('r' + q + val + q)
        valid = []
        for cand in candidates:
            try:
                if ast.literal_eval(cand) == val:
                    valid.append(cand)
            except Exception:
                pass
        if valid:
            return min(valid, key=len)
    elif isinstance(val, bytes):
        candidates = []
        candidates.append(repr(val))
        for q in ["'", '"']:
            try:
                parts = []
                for b in val:
                    c = chr(b)
                    if c == '\\':
                        parts.append('\\\\')
                    elif c == q:
                        parts.append('\\' + q)
                    elif c == '\n':
                        parts.append('\\n')
                    elif c == '\r':
                        parts.append('\\r')
                    elif c == '\t':
                        parts.append('\\t')
                    elif 32 <= b <= 126:
                        parts.append(c)
                    else:
                        parts.append('\\x{:02x}'.format(b))
                candidates.append('b' + q + ''.join(parts) + q)
            except Exception:
                pass
        for q in ["'", '"']:
            if val and val[-1] == ord('\\'):
                continue
            if ord(q) in val:
                continue
            if any(not (32 <= b <= 126) for b in val):
                continue
            try:
                candidates.append('br' + q + val.decode('ascii') + q)
            except Exception:
                pass
        valid = []
        for cand in candidates:
            try:
                if ast.literal_eval(cand) == val:
                    valid.append(cand)
            except Exception:
                pass
        if valid:
            return min(valid, key=len)
    return None

class UnicodeEscapeExpander(ConstantTransformer):
    def visit_Str(self, node):
        opt = get_shortest_literal(node.s)
        if opt is not None:
            node.raw_representation = opt
        return node

    def visit_Bytes(self, node):
        opt = get_shortest_literal(node.s)
        if opt is not None:
            node.raw_representation = opt
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, (str, bytes)):
            opt = get_shortest_literal(node.value)
            if opt is not None:
                node.raw_representation = opt
        return node

class CollectionLiteralFolder(ConstantTransformer):
    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and not node.keywords:
            parent = get_parent(node)
            if node.func.id == 'list' and len(node.args) == 0:
                return self.add_child(ast.List(elts=[], ctx=ast.Load()), parent=parent, namespace=node.namespace)
            elif node.func.id == 'dict' and len(node.args) == 0:
                return self.add_child(ast.Dict(keys=[], values=[]), parent=parent, namespace=node.namespace)
            elif node.func.id == 'tuple' and len(node.args) == 0:
                return self.add_child(ast.Tuple(elts=[], ctx=ast.Load()), parent=parent, namespace=node.namespace)
            elif node.func.id == 'set' and len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, (ast.List, ast.Tuple)):
                    if len(arg.elts) > 0:
                        return self.add_child(ast.Set(elts=arg.elts), parent=parent, namespace=node.namespace)
        return node

class BooleanSimplifier(ConstantTransformer):
    def visit_UnaryOp(self, node):
        node = self.generic_visit(node)
        if isinstance(node.op, ast.Not):
            if isinstance(node.operand, ast.Compare) and len(node.operand.ops) == 1:
                op = node.operand.ops[0]
                if isinstance(op, ast.Is):
                    node.operand.ops[0] = ast.IsNot()
                    return node.operand
                elif isinstance(op, ast.IsNot):
                    node.operand.ops[0] = ast.Is()
                    return node.operand
                elif isinstance(op, ast.In):
                    node.operand.ops[0] = ast.NotIn()
                    return node.operand
                elif isinstance(op, ast.NotIn):
                    node.operand.ops[0] = ast.In()
                    return node.operand
        return node

    def visit_Compare(self, node):
        node = self.generic_visit(node)
        if len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            left = node.left
            right = node.comparators[0]
            if isinstance(right, ast.NameConstant) and right.value in (True, False):
                parent = get_parent(node)
                if right.value is True:
                    return left
                else:
                    return self.add_child(ast.UnaryOp(op=ast.Not(), operand=left), parent=parent, namespace=node.namespace)
            elif isinstance(left, ast.NameConstant) and left.value in (True, False):
                parent = get_parent(node)
                if left.value is True:
                    return right
                else:
                    return self.add_child(ast.UnaryOp(op=ast.Not(), operand=right), parent=parent, namespace=node.namespace)
        return node

class FoldConstants(SuiteTransformer):
    def __init__(self, options=None):
        super(FoldConstants, self).__init__()
        self.options = options or {}

    def __call__(self, node):
        # Run sub-transformers in order
        pipeline = [
            DebugConstantTransformer(self.options),
            NumberRepresentationOptimizer(self.options),
            EnvironmentConstantTransformer(self.options),
            ExpressionFolder(self.options),
            UnicodeEscapeExpander(self.options),
            CollectionLiteralFolder(self.options),
            BooleanSimplifier(self.options)
        ]
        for transformer in pipeline:
            node = transformer(node)
        return node
