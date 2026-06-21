from terser.terser import minify, unparse, UnstableMinification, minify_project
from terser.transforms.remove_annotations_options import RemoveAnnotationsOptions

__all__ = [
    'minify',
    'minify_project',
    'unparse',
    'UnstableMinification',
    'RemoveAnnotationsOptions'
]
