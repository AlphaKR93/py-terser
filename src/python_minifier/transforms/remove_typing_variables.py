import python_minifier.ast as ast

from python_minifier.transforms.suite_transformer import SuiteTransformer


class RemoveTypingVariables(SuiteTransformer):
    """
    Remove or simplify type annotations from source to reduce code size.
    """

    def __init__(self):
        super(RemoveTypingVariables, self).__init__()

    def visit_Assign(self, node):
        """
        Assign 노드를 방문하여 대입 대상(target)을 확인하고 수정합니다.
        """
        # 1. 대입 대상(targets)이 정확히 하나인지 확인합니다.
        if len(node.targets) != 1:
            # 여러 타겟이거나 (a, b = c) 언패킹 대입 (a, *b = c)은 건너뜁니다.
            return self.generic_visit(node)

        target = node.targets[0]

        # 2. 타겟이 ast.Name 노드이며 이름이 '_'인지 확인합니다.
        # 또한, 해당 Name 노드가 대입(Store) 컨텍스트에 있는지 확인합니다.
        if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
            if target.id == "_":
                # 대입문 제거 및 value(함수 호출)만 남기기:
                # ast.Assign 노드를 ast.Expr 노드로 대체합니다.
                new_node = ast.Expr(value=node.value)

                # 원래 노드의 정보를 새 노드에 복사합니다 (라인 번호 등).
                # ast.copy_location은 관례적으로 사용되어 디버깅에 도움이 됩니다.
                return ast.copy_location(new_node, node)
            elif target.id == "__all__":
                return ast.Pass()

        # 조건에 해당하지 않는 Assign 노드는 그대로 둡니다.
        return self.generic_visit(node)
