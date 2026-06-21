from dataclasses import dataclass

import terser._ast as ast
from terser._ast.annotation import add_parent
from terser.config import TerserConfig
from terser.transforms.constant_folding import (
    DebugConstantTransformer,
    EnvironmentConstantTransformer,
    ExpressionFolder
)
from terser.transforms.remove_dead_blocks import RemoveDeadBlocks

@dataclass
class ParseResult:
    module: ast.Module

class Parser:
    def __init__(self, config: TerserConfig):
        self.config = config

    def parse(self, source: str, filename: str) -> ParseResult:
        try:
            module = ast.parse(source, filename)
        except Exception as e:
            # Raise with filename included in error
            raise RuntimeError(f"Failed to parse {filename}: {e}") from e

        import os
        setattr(module, 'is_init', os.path.basename(filename) == '__init__.py')

        add_parent(module)
        from terser.rename import add_namespace
        add_namespace(module)

        if self.config.fold_constants:
            # Prepare options for the constant folding subset
            # __debug__ -> False if config.optimize is True (merged remove-asserts + remove-debug)
            # platform and version_info from config
            options = {
                'remove_debug': self.config.optimize,
                'version_info': self.config.version_info,
                'platform': self.config.platform
            }

            # Apply early constant folding subset
            module = DebugConstantTransformer(options)(module)
            module = EnvironmentConstantTransformer(options)(module)
            module = ExpressionFolder(options)(module)

            # Recurse add_parent to restore correct links
            add_parent(module)

            # Apply early RemoveDeadBlocks
            module = RemoveDeadBlocks()(module)
            add_parent(module)

        return ParseResult(module)
