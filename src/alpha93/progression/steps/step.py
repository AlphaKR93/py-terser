from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import StepContext


class Step:
    def __init__(self, ctx: StepContext):
        self.ctx = ctx
