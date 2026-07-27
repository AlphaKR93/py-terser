from typing import TYPE_CHECKING, override

from terser.ast import ast
from ._suite import SuiteTransformer, TransformerFlag

if TYPE_CHECKING:
    from terser.config import TransformConfig


class RemovePosArgs(SuiteTransformer):
    """
    Convert positional-only arguments to normal arguments
    """
    FLAGS = TransformerFlag.INFLUENCES_MANGLING

    @override
    @classmethod
    def is_enabled(cls, config: "TransformConfig", /) -> bool:
        return config.convert_posargs

    @override
    def visit_arguments(self, node: ast.arguments):
        node: ast.arguments = self.generic_visit(node)

        if hasattr(node, 'posonlyargs') and node.posonlyargs:
            node.args = node.posonlyargs + node.args
            node.posonlyargs = []

        return node
