import terser._ast as ast
from terser.config import TerserConfig
from terser.rename import (
    add_namespace,
    bind_names,
    resolve_names,
    allow_rename_locals,
    allow_rename_globals,
    rename_literals,
    rename
)
from terser.transforms.local_reference_aliasing import LocalReferenceAliaser
from terser.transforms.dynamic_import_renamer import DynamicImportRenamer

class Mangler:
    def __init__(self, config: TerserConfig):
        self.config = config

    def mangle(self, module: ast.Module) -> ast.Module:
        # Re-bind and resolve name scopes before mangling
        add_namespace(module)
        bind_names(module)
        resolve_names(module)

        # Handle tainted namespace (e.g. exec/eval used)
        rename_globals = self.config.rename_globals
        rename_locals = self.config.rename_locals
        if getattr(module, 'tainted', False):
            rename_globals = False
            rename_locals = False

        # 1. Filter preserve_globals
        preserve_globals = []
        for item in (self.config.preserve_globals or []):
            if ':' in item:
                mod_part, name_part = item.split(':', 1)
                curr_mod = self.config.current_module_name or ""
                if curr_mod == mod_part or curr_mod.endswith('.' + mod_part):
                    preserve_globals.append(name_part)
            else:
                preserve_globals.append(item)

        preserve_locals = list(self.config.preserve_locals or [])

        # Add module preserved names
        module_preserved = getattr(module, 'preserved', [])
        preserve_locals.extend(module_preserved)
        preserve_globals.extend(module_preserved)

        # Add module name map values to preserve_globals to avoid double mangling
        if self.config.module_name_map:
            preserve_globals.extend(self.config.module_name_map.values())

        # 2. Allow rename settings
        allow_rename_locals(module, rename_locals, preserve_locals)
        allow_rename_globals(module, rename_globals, preserve_globals, ignore_all=self.config.ignore_all)

        # 3. Rename literals (hoist literals rename)
        if self.config.hoist_literals:
            rename_literals(module)

        # 4. Perform the name mangling
        rename(module, prefix_globals=not rename_globals, preserved_globals=preserve_globals)

        # 5. LocalReferenceAliaser (runs after renaming to alias frequent names)
        module = LocalReferenceAliaser()(module)

        # 6. DynamicImportRenamer (runs to update dynamic imports using rename_map)
        if self.config.rename_map:
            module = DynamicImportRenamer(self.config.rename_map)(module)

        # 7. Populate obfuscation_map if config.obfuscation_map is a dict
        if isinstance(self.config.obfuscation_map, dict):
            from terser.rename.renamer import sorted_bindings
            for _namespace, binding in sorted_bindings(module):
                if binding.original_name and binding.name and binding.name != binding.original_name:
                    self.config.obfuscation_map[binding.original_name] = binding.name

        return module
