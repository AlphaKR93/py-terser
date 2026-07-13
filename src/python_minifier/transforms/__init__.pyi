from collections.abc import Iterable
from typing import Callable

from python_minifier.config import TransformConfig
from .suite_transformer import SuiteTransformer

__transforms__: Iterable[Callable[[TransformConfig], SuiteTransformer]]
