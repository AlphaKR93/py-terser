from collections.abc import Iterable
from typing import Callable

from terser.config import TransformConfig
from terser._pipeline.transforms.suite_transformer import SuiteTransformer

__transforms__: Iterable[Callable[[TransformConfig], SuiteTransformer]]
