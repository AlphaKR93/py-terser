import terser._ast as ast
from terser.transforms.suite_transformer import SuiteTransformer
from terser.transforms.constant_folding import unparse_expression
from terser.transforms.general_minifications import is_side_effect_free

class LambdaConverter(SuiteTransformer):
    """
    Convert single-expression, no-decorator, no-docstring functions to lambdas when smaller.
    """
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
        
        cleaned = []
        for node in visited_list:
            if isinstance(node, ast.FunctionDef) and not node.decorator_list:
                if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
                    ret = node.body[0]
                    args_spec = node.args
                    defaults_safe = True
                    if args_spec.defaults:
                        for d in args_spec.defaults:
                            if not is_side_effect_free(d):
                                defaults_safe = False
                                break
                    if hasattr(args_spec, 'kw_defaults') and args_spec.kw_defaults:
                        for d in args_spec.kw_defaults:
                            if d is not None and not is_side_effect_free(d):
                                defaults_safe = False
                                break
                    
                    if defaults_safe:
                        ret_val = ret.value if ret.value is not None else self.add_child(ast.NameConstant(value=None), parent=node, namespace=node.namespace)
                        new_lambda = self.add_child(ast.Lambda(args=node.args, body=ret_val), parent=parent, namespace=node.namespace)
                        new_target = self.add_child(ast.Name(id=node.name, ctx=ast.Store()), parent=parent, namespace=node.namespace)
                        new_assign = self.add_child(ast.Assign(targets=[new_target], value=new_lambda), parent=parent, namespace=node.namespace)
                        
                        try:
                            orig_len = len(unparse_expression(node))
                            new_len = len(unparse_expression(new_assign))
                            if new_len < orig_len:
                                cleaned.append(new_assign)
                                continue
                        except Exception:
                            pass
            cleaned.append(node)
        return cleaned
