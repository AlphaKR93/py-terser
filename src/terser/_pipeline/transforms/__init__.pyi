from collections.abc import Iterable
from typing import Callable

from terser.config import TransformConfig
from terser._pipeline.transforms._suite import SuiteTransformer

__transforms__: Iterable[Callable[[TransformConfig], SuiteTransformer]]
