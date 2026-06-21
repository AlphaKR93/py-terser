import terser._ast as ast
from terser.config import TerserConfig
from terser._ast.annotation import add_parent
from terser.rename import add_namespace, bind_names, resolve_names

# Import all passes
from terser.transforms.constant_folding import FoldConstants
from terser.transforms.contracts import Contracts
from terser.transforms.inline_lambda_invoke import InlineLambdaInvoke
from terser.transforms.remove_dummy_variables import RemoveDummyVariables
from terser.transforms.remove_explicit_fields import RemoveExplicitFields
from terser.transforms.remove_dead_blocks import RemoveDeadBlocks
from terser.transforms.remove_docstrings import RemoveDocstrings
from terser.transforms.remove_overloads import RemoveOverloads
from terser.transforms.remove_explicit_inherits import RemoveExplicitInherits
from terser.transforms.remove_bare_protocols import RemoveBareProtocols
from terser.transforms.remove_generics import RemoveGenerics
from terser.transforms.remove_annotations import RemoveAnnotations
from terser.transforms.remove_asserts import RemoveAsserts
from terser.transforms.remove_type_stmt import RemoveTypeStmt
from terser.transforms.remove_trailing_returns import RemoveTrailingReturns
from terser.transforms.simplify_posargs import SimplifyPositionArguments
from terser.transforms.simplify_dynamic_attrs import SimplifyDynamicAttributes
from terser.transforms.simplify_fstring import SimplifyFString
from terser.transforms.simplify_early_exit import SimplifyEarlyExit
from terser.transforms.simplify_raise import SimplifyRaise
from terser.transforms.simplify_if_stmt import SimplifyIfStmt
from terser.transforms.convert_to_ternary import ConvertToTernary
from terser.transforms.convert_to_lambda import ConvertToLambda
from terser.transforms.hoist_literals import HoistLiterals
from terser.transforms.remove_pass import RemovePass
from terser.transforms.remove_typing_decorators import RemoveTypingDecorators
from terser.transforms.inline_functions import InlineFunctions
from terser.transforms.inline_int_flags import InlineIntFlags
from terser.transforms.cleanup_imports import CleanupImports

class TransformRunner:
    def __init__(self, config: TerserConfig):
        self.config = config

    def run(self, module: ast.Module) -> ast.Module:
        fold_options = {
            'remove_debug': self.config.optimize,
            'version_info': self.config.version_info,
            'platform': self.config.platform
        }

        # List of passes, their config gate, and the instantiated pass
        passes = [
            (self.config.fold_constants, lambda: FoldConstants(options=fold_options)),
            (self.config.optimize, lambda: Contracts()),
            (True, lambda: InlineLambdaInvoke()),
            (True, lambda: RemoveDummyVariables()),
            (self.config.remove_annotations, lambda: RemoveExplicitFields()),
            (True, lambda: RemoveDeadBlocks()),
            (self.config.remove_docstrings, lambda: RemoveDocstrings(strict=self.config.strict_docstrings)),
            (self.config.remove_annotations, lambda: RemoveOverloads()),
            (self.config.remove_explicit_inherits, lambda: RemoveExplicitInherits()),
            (self.config.remove_annotations, lambda: RemoveBareProtocols()),
            (self.config.remove_annotations, lambda: RemoveGenerics()),
            (self.config.remove_annotations, lambda: RemoveAnnotations(
                options=__import__("terser.transforms.remove_annotations_options", fromlist=["RemoveAnnotationsOptions"]).RemoveAnnotationsOptions(
                    remove_variable_annotations=self.config.remove_variable_annotations,
                    remove_return_annotations=self.config.remove_return_annotations,
                    remove_argument_annotations=self.config.remove_argument_annotations,
                    remove_class_attribute_annotations=self.config.remove_class_attribute_annotations,
                )
            )),
            (self.config.optimize, lambda: RemoveAsserts()),
            (self.config.remove_type_stmt, lambda: RemoveTypeStmt()),
            (self.config.remove_trailing_returns, lambda: RemoveTrailingReturns()),
            (self.config.simplify_posargs, lambda: SimplifyPositionArguments()),
            (self.config.simplify_dynamic_attrs, lambda: SimplifyDynamicAttributes()),
            (self.config.simplify_fstring, lambda: SimplifyFString()),
            (self.config.simplify_early_exit, lambda: SimplifyEarlyExit()),
            (self.config.simplify_raise, lambda: SimplifyRaise()),
            (self.config.simplify_if_stmt, lambda: SimplifyIfStmt()),
            (self.config.convert_to_ternary, lambda: ConvertToTernary()),
            (self.config.convert_to_lambda, lambda: ConvertToLambda()),
            (self.config.hoist_literals, lambda: HoistLiterals()),
            (True, lambda: RemovePass()),
            (self.config.remove_annotations, lambda: RemoveTypingDecorators()),
            (self.config.inline_functions, lambda: InlineFunctions()),
            (self.config.inline_int_flags, lambda: InlineIntFlags()),
            (self.config.cleanup_imports, lambda: CleanupImports(self.config)),
        ]

        for cycle in range(self.config.transform_passes):
            # Run add_parent + add_namespace before each cycle
            add_parent(module)
            add_namespace(module)
            bind_names(module)
            resolve_names(module)

            for enabled, pass_factory in passes:
                if enabled:
                    pass_instance = pass_factory()
                    module = pass_instance(module)

        # Remove __all__ after final pass cycle if not referenced
        has_all_read = False
        for sub in ast.walk(module):
            if isinstance(sub, ast.Name) and sub.id == '__all__' and isinstance(sub.ctx, ast.Load):
                has_all_read = True
                break

        if not has_all_read:
            module.body = [
                s for s in module.body
                if not (
                    isinstance(s, ast.Assign)
                    and len(s.targets) == 1
                    and isinstance(s.targets[0], ast.Name)
                    and s.targets[0].id == '__all__'
                )
            ]

        return module
