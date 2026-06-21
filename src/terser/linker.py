from pathlib import Path
import terser._ast as ast
from terser.config import TerserConfig
from terser.rename import (
    add_namespace,
    bind_names,
    resolve_names
)
from terser.transforms.module_obfuscator import ImportedNamesCollector, ModuleObfuscator

class Linker:
    def __init__(self, config: TerserConfig):
        self.config = config

    def link(self, module: ast.Module, path: Path | None = None) -> ast.Module:
        add_namespace(module)
        bind_names(module)
        resolve_names(module)

        # Cross-module obfuscation
        if self.config.module_name_map:
            current_mod = self.config.current_module_name
            if not current_mod and path:
                # Deduce module name from path stem
                current_mod = path.stem

            collector = ImportedNamesCollector(current_mod)
            collector.visit(module)

            obfuscator = ModuleObfuscator(
                self.config.module_name_map,
                current_mod,
                collector.imported_modules,
                user_modules=self.config.user_modules
            )
            module = obfuscator.visit(module)

            # Re-bind and resolve after AST modification
            add_namespace(module)
            bind_names(module)
            resolve_names(module)

        return module
