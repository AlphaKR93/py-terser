from typing import TYPE_CHECKING, override

from terser.ast_compat import NodeVisitor, ast

if TYPE_CHECKING:
    from terser._pipeline.parser.ref import ModuleRef


class ImportResolver(NodeVisitor):
    module_ref: ModuleRef

    def __call__(self, module_ref: ModuleRef):
        self.module_ref = module_ref
        return self.visit(module_ref._ast)

    @override
    def visit_Import(self, node: ast.Import):
        for name in node.names:
            self.module_ref.imports[name.asname or name.name] = name

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom):
        for name in node.names:
            self.module_ref.imports[name.asname or name.name] = name

    @override
    def visit_Assign(self, node: ast.Assign):
        if len(node.targets) != 1 or not isinstance(target := node.targets[0], ast.Name):
            return
        if not isinstance(call := node.value, ast.Call):
            return
        if not isinstance(func := call.func, ast.Name) or func.id not in ("__import__", "__lazy_import__"):
            return

        self.module_ref.imports[target.id] = node
