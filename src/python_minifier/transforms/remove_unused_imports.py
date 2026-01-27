import python_minifier.ast as ast

from python_minifier.transforms.suite_transformer import SuiteTransformer
from python_minifier.util import is_constant_node


def remove_unused_imports(module, preserved):
    collector = UsedNameCollector()
    collector.visit(module)
    return UnusedImportRemover(collector.used_names | preserved)(module)


class UsedNameCollector(ast.NodeVisitor):
    """
    AST를 순회하며 코드에서 사용된 모든 이름을 수집합니다.
    """

    def __init__(self):
        self.used_names = set()

    def visit_Name(self, node):
        """
        Name 노드를 방문하여 로드(load) 컨텍스트의 이름을 수집합니다.
        Store(할당)나 Del(삭제) 컨텍스트의 이름은 import 사용을 나타내지 않습니다.
        """
        # ast.Load 컨텍스트일 때만 이름이 사용된 것으로 간주합니다.
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)

        # 기본 visit 메서드를 호출하여 자식 노드를 계속 순회합니다.
        self.generic_visit(node)

    def visit_Attribute(self, node):
        """
        속성 접근(예: 'os.path.join')을 처리하여 최상위 모듈 이름을 수집합니다.
        """
        # 속성 접근의 루트 객체를 재귀적으로 찾습니다.
        # 예: 'a.b.c'에서 'a'를 찾습니다.
        current = node.value
        while isinstance(current, ast.Attribute):
            current = current.value

        if isinstance(current, ast.Name):
            # 최상위 이름이 로드 컨텍스트에 있으면 사용된 것으로 간주합니다.
            if isinstance(current.ctx, ast.Load):
                self.used_names.add(current.id)

        self.generic_visit(node)

    def _extract_names_from_all(self, value_node):
        """
        __all__ 리스트/튜플에서 문자열 상수를 추출하여 used_names에 추가합니다.
        """
        if isinstance(value_node, (ast.List, ast.Tuple)):
            for elt in value_node.elts:
                if is_constant_node(elt, ast.Str):
                    # 문자열 상수의 값을 사용된 이름으로 추가
                    if hasattr(elt, "value") and isinstance(elt.value, str):
                        self.used_names.add(elt.value)
                    elif hasattr(elt, "s"):
                        self.used_names.add(elt.s)

    def visit_Assign(self, node):
        """
        __all__ = [...] 형태를 처리합니다.
        """
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                self._extract_names_from_all(node.value)

        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        """
        __all__: list[str] = [...] 형태를 처리합니다.
        """
        if isinstance(node.target, ast.Name) and node.target.id == "__all__":
            if node.value:
                self._extract_names_from_all(node.value)

        self.generic_visit(node)

    def visit_AugAssign(self, node):
        """
        __all__ += [...] 형태를 처리합니다.
        """
        if isinstance(node.target, ast.Name) and node.target.id == "__all__":
            self._extract_names_from_all(node.value)

        self.generic_visit(node)


class UnusedImportRemover(SuiteTransformer):
    """
    수집된 사용된 이름을 기반으로 사용되지 않는 import 문을 제거하거나 수정합니다.
    """

    def __init__(self, used_names):
        self.used_names = used_names
        super(UnusedImportRemover, self).__init__()

    def visit_Import(self, node):
        """
        `import module, module as alias` 형태의 Import 노드를 처리합니다.
        """
        new_names = []

        # import 되는 각 이름/별칭을 확인합니다.
        for alias in node.names:
            imported_name = alias.asname if alias.asname else alias.name.split(".")[0]

            # import된 이름이 코드에서 사용되었는지 확인합니다.
            if imported_name in self.used_names:
                new_names.append(alias)

        if not new_names:
            # 모든 import 이름이 사용되지 않으면, 노드를 제거합니다.
            return ast.Pass()
        elif len(new_names) < len(node.names):
            # 일부 import만 사용된 경우, 노드의 names 목록을 수정합니다.
            node.names = new_names
            return node
        else:
            # 모든 import가 사용된 경우, 노드를 그대로 유지합니다.
            return node

    def visit_ImportFrom(self, node):
        """
        `from module import name, name as alias` 형태의 ImportFrom 노드를 처리합니다.
        """
        # 'from . import ...'와 같은 상대 경로 import는 건너뜁니다.
        if node.level > 0 and node.module is None:
            return node

        new_names = []

        for alias in node.names:
            imported_name = alias.asname if alias.asname else alias.name

            # from ... import * 구문은 명시적으로 처리하지 않습니다. (제거하지 않음)
            if alias.name == "*":
                new_names.append(alias)
                continue

            # import된 이름이 코드에서 사용되었는지 확인합니다.
            if imported_name in self.used_names:
                new_names.append(alias)

        if not new_names:
            # 모든 import 이름이 사용되지 않으면, 노드를 제거합니다.
            return ast.Pass()
        elif len(new_names) < len(node.names):
            # 일부 import만 사용된 경우, 노드의 names 목록을 수정합니다.
            node.names = new_names
            return node
        else:
            # 모든 import가 사용된 경우, 노드를 그대로 유지합니다.
            return node
