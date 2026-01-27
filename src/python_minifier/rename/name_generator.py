import itertools
import keyword
import random
import string

from .util import builtins


def random_generator(length=40):
    valid_first = string.ascii_uppercase + string.ascii_lowercase
    valid_rest = string.digits + valid_first + "_"

    while True:
        first = [random.choice(valid_first)]
        rest = [random.choice(valid_rest) for i in range(length - 1)]
        yield "".join(first + rest)


def get_valid_2byte_chars():
    """
    Get valid identifier start characters that are 2 bytes in UTF-8
    """
    valid = []
    # Basic Multilingual Plane ranges that are generally valid and often 2 bytes
    # U+0080 to U+07FF are 2 bytes in UTF-8.
    # We check isidentifier() to be safe and exclude whitespace.
    for i in range(0x0080, 0x0800):
        c = chr(i)
        if c.isidentifier() and not c.isspace():
            valid.append(c)
    return valid


def name_generator(allow_unicode=False):
    valid_first = string.ascii_uppercase + string.ascii_lowercase
    valid_rest = string.digits + valid_first + "_"

    unicode_chars = []
    if allow_unicode:
        unicode_chars = get_valid_2byte_chars()

    # 1. Yield 1-byte ASCII chars
    for c in valid_first:
        yield c

    # 2. Yield 2-byte Unicode chars (if allowed)
    for c in unicode_chars:
        yield c

    # Prepare for combinations
    if allow_unicode:
        # We append unicode chars to valid sets so itertools.product uses them
        valid_first += "".join(unicode_chars)
        valid_rest += "".join(unicode_chars)

    for length in itertools.count(1):
        for first in valid_first:
            for rest in itertools.product(valid_rest, repeat=length):
                name = first
                name += "".join(rest)
                yield name


def name_filter(allow_unicode=False):
    """
    Yield all valid python identifiers

    Name are returned sorted by length, then string sort order.

    Names that already have meaning in python (keywords and builtins)
    will not be included in the output.

    :param bool allow_unicode: If True, generate names using unicode characters
    :rtype: Iterable[str]

    """

    reserved = keyword.kwlist + dir(builtins)

    for name in name_generator(allow_unicode=allow_unicode):
        if name not in reserved:
            yield name
