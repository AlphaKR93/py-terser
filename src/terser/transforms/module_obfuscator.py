import terser.ast_compat as ast

class ImportedNamesCollector(ast.NodeVisitor):
    def __init__(self, current_module_name=None):
        self.imported_names = set()
        self.imported_modules = {}
        self.current_module_name = current_module_name

    def visit_Import(self, node):
        for alias in node.names:
            parts = alias.name.split('.')
            self.imported_names.add(alias.asname or parts[0])
            
            local_name = alias.asname or parts[0]
            if alias.asname:
                self.imported_modules[local_name] = alias.name
            else:
                self.imported_modules[local_name] = parts[0]

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.imported_names.add(alias.asname or alias.name)
            
        prefix = ""
        if node.module:
            prefix = node.module
        if node.level > 0 and self.current_module_name:
            curr_parts = self.current_module_name.split('.')
            pkg_parts = curr_parts[:-node.level] if len(curr_parts) >= node.level else []
            if prefix:
                prefix = '.'.join(pkg_parts + [prefix])
            else:
                prefix = '.'.join(pkg_parts)
                
        for alias in node.names:
            local_name = alias.asname or alias.name
            self.imported_modules[local_name] = prefix + '.' + alias.name if prefix else alias.name


def resolve_absolute_import_from(level, module, current_module):
    prefix = module or ""
    if level > 0 and current_module:
        curr_parts = current_module.split('.')
        pkg_parts = curr_parts[:-level] if len(curr_parts) >= level else []
        if prefix:
            return '.'.join(pkg_parts + [prefix])
        else:
            return '.'.join(pkg_parts)
    return prefix


def is_module_ref(node, imported_names):
    if isinstance(node, ast.Name):
        return node.id in imported_names
    if isinstance(node, ast.Attribute):
        return is_module_ref(node.value, imported_names)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == '__import__':
            if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                return True
    return False


class ModuleObfuscator(ast.NodeTransformer):
    def __init__(self, module_name_map, current_module_name, imported_modules, user_modules=None):
        self.module_name_map = module_name_map or {}
        self.current_module_name = current_module_name
        self.user_modules = user_modules
        self.reverse_module_name_map = {v: k for k, v in self.module_name_map.items()}
        
        if isinstance(imported_modules, dict):
            self.imported_modules = imported_modules
            self.imported_names = set(imported_modules.keys())
        else:
            self.imported_modules = {}
            self.imported_names = set(imported_modules or [])
        
        if current_module_name:
            parts = current_module_name.split('.')
            new_parts = [self.module_name_map.get(p, p) for p in parts]
            self.obfuscated_module_name = '.'.join(new_parts)
            self.obfuscated_package_name = '.'.join(new_parts[:-1]) if len(new_parts) > 1 else ""
        else:
            self.obfuscated_module_name = None
            self.obfuscated_package_name = None

    def obfuscate_string(self, s):
        if not s:
            return s
        # Obfuscate dotted module name string references (like in dynamic imports or sys.modules)
        parts = s.split('.')
        new_parts = [self.module_name_map.get(p, p) for p in parts]
        return '.'.join(new_parts)

    def visit_ClassDef(self, node):
        if node.name in self.module_name_map:
            node.name = self.module_name_map[node.name]
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name in self.module_name_map:
            node.name = self.module_name_map[node.name]
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if node.name in self.module_name_map:
            node.name = self.module_name_map[node.name]
        return self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if self.user_modules:
                parts = alias.name.split('.')
                is_user = False
                for i in range(1, len(parts) + 1):
                    prefix = '.'.join(parts[:i])
                    if prefix in self.user_modules:
                        is_user = True
                        break
                if not is_user:
                    continue
            
            parts = alias.name.split('.')
            new_parts = [self.module_name_map.get(p, p) for p in parts]
            alias.name = '.'.join(new_parts)
            if alias.asname is not None:
                new_asname = self.module_name_map.get(alias.asname, alias.asname)
                # Clear asname if it would be same as top-level module name (import X as X)
                alias.asname = None if new_asname == new_parts[0] else new_asname
            else:
                # Only set asname for dotted imports (import a.b → import x.y as x)
                if len(parts) > 1:
                    new_top = self.module_name_map.get(parts[0], parts[0])
                    alias.asname = new_top if new_top != new_parts[0] else None
        return node

    def visit_ImportFrom(self, node):
        abs_module = resolve_absolute_import_from(node.level, node.module, self.current_module_name)
        is_user_module = False
        if self.user_modules:
            if abs_module in self.user_modules:
                is_user_module = True
        else:
            is_user_module = True
            
        if is_user_module:
            if node.module is not None:
                parts = node.module.split('.')
                new_parts = [self.module_name_map.get(p, p) for p in parts]
                node.module = '.'.join(new_parts)
            for alias in node.names:
                if alias.name in self.module_name_map:
                    original_name = alias.name
                    alias.name = self.module_name_map[original_name]
                    if alias.asname is not None:
                        alias.asname = self.module_name_map.get(alias.asname, alias.asname)
                else:
                    if alias.asname is not None:
                        alias.asname = self.module_name_map.get(alias.asname, alias.asname)
        return node

    def visit_Name(self, node):
        if node.id == '__name__':
            parent = getattr(node, '_parent', None)
            is_main_comparison = False
            if isinstance(parent, ast.Compare):
                for cmp in [parent.left] + parent.comparators:
                    if isinstance(cmp, ast.Constant) and cmp.value == '__main__':
                        is_main_comparison = True
                    elif isinstance(cmp, ast.Str) and cmp.s == '__main__':
                        is_main_comparison = True
            if not is_main_comparison and self.obfuscated_module_name:
                return ast.Constant(value=self.obfuscated_module_name)
        elif node.id == '__package__':
            if self.obfuscated_package_name is not None:
                return ast.Constant(value=self.obfuscated_package_name)
        elif node.id in self.module_name_map:
            node.id = self.module_name_map[node.id]
        return node

    def resolve_absolute_name(self, node):
        if isinstance(node, ast.Name):
            if node.id in self.imported_modules:
                return self.imported_modules[node.id]
            if node.id == self.current_module_name:
                return self.current_module_name
            return node.id
        if isinstance(node, ast.Attribute):
            val = self.resolve_absolute_name(node.value)
            if val:
                return val + '.' + node.attr
            return node.attr
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == '__import__':
                if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                    val = node.args[0].value if isinstance(node.args[0], ast.Constant) else node.args[0].s
                    if val:
                        # The string arg is always the original module name at this point
                        # (visit_Call has not yet obfuscated it). Use directly.
                        return val
        return None

    def visit_Attribute(self, node):
        abs_name = self.resolve_absolute_name(node)
        if self.user_modules:
            is_ref = False
            if abs_name in self.user_modules:
                is_ref = True
            else:
                prefix = self.resolve_absolute_name(node.value)
                if prefix in self.user_modules:
                    is_ref = True
        else:
            is_ref = is_module_ref(node.value, self.imported_names)
            
        node.value = self.visit(node.value)
        if node.attr in self.module_name_map and is_ref:
            node.attr = self.module_name_map[node.attr]
        return node

    def obfuscate_arg_node(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = self.obfuscate_string(node.value)
        elif isinstance(node, ast.Str):
            node.s = self.obfuscate_string(node.s)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == '__import__':
            if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                self.obfuscate_arg_node(node.args[0])
        elif isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module':
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'importlib':
                if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                    self.obfuscate_arg_node(node.args[0])
        return self.generic_visit(node)

    def visit_Subscript(self, node):
        if isinstance(node.value, ast.Attribute) and node.value.attr == 'modules':
            if isinstance(node.value.value, ast.Name) and node.value.value.id == 'sys':
                slice_node = node.slice
                if isinstance(slice_node, ast.Index):
                    slice_node = slice_node.value
                if isinstance(slice_node, (ast.Constant, ast.Str)):
                    self.obfuscate_arg_node(slice_node)
        return self.generic_visit(node)
