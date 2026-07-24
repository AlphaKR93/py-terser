from __future__ import annotations  # FIXME: ty complains

from typing import TYPE_CHECKING, final


if TYPE_CHECKING:
    from typing import Final


@final
class Namespace:
    parent: Final[Namespace | None]
    level: Final[int]
    name: Final[str]

    def __init__(self, path: str):
        if '.' not in path:
            self.name = path
            self.parent = None
            self.level = 0
            return

        parent, self.name = path.rsplit('.', 1)
        self.parent = Namespace(parent)
        self.level = self.parent.level + 1

    def __str__(self):
        return (str(self.parent) + '.' + self.name) if self.parent else self.name
