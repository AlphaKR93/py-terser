from typing import override, TYPE_CHECKING

from terser.ast import ast, ref
from terser.utils import contracts
from ..resolver.binding import ImportBinding
from ._suite import SuiteTransformer, TransformerFlag

if TYPE_CHECKING:
    from ...config import TransformConfig


class Contracts(SuiteTransformer):
    FLAGS = TransformerFlag.REQUIRES_IMPORT_RESOLVE

    _contracts: dict[str, contracts.Contract]

    def __init__(self, ctx, /):
        super().__init__(ctx)
        _contracts = {c.name: c for c in map(contracts.parse, self._config.contracts)}  # TODO: Move to global

    @override
    @classmethod
    def is_enabled(cls, config: TransformConfig) -> bool:
        return config.apply_contracts

    @override
    def visit_Expr(self, node: ast.Expr):
        node.value = self.visit(node.value)
        return None if node.value is None else node

    @override
    def visit_Call(self, node: ast.Call):
        node: ast.Call = self.generic_visit(node)
        node_ref = ref(node)
        binding = node_ref.binding

        contract: contracts.Contract
        if (name0 := binding.name) and name0 in self._contracts:
            contract = self._contracts[name0]
            del name0
        else:
            if not isinstance(binding, ImportBinding):
                return node

            name1 = f"{binding.source_module}.{binding.name}"
            if name1 not in self._contracts:
                return node

            contract = self._contracts[name1]
            del name1

        if not contract.convert_to:
            return self.add_child(ast.Constant(value=None), parent=node_ref.parent, namespace=node_ref.namespace)

        assert isinstance(contract.args, list)

        preserved = {}
        for i, name in enumerate(contract.args):
            if not name:
                continue

            preserved[name] = node.args[i]

        return contract.convert(**preserved)
