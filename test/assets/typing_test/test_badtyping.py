"""
This should fail type checking
"""

from terser import minify


def test_typing() -> None:

    minify(
        456,
        remove_pass='yes please'
    )
