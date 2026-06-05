import python_minifier.ast_compat as ast
import keyword
import string

from hypothesis.strategies import booleans, composite, integers, lists, none, one_of, recursive, sampled_from, text


@composite
def name(draw):
    # Generate simple ASCII names that avoid keywords
    n = draw(text(alphabet=string.ascii_letters, min_size=1, max_size=3))

    # Handle keywords by prefixing with underscore instead of filtering
    if n in keyword.kwlist:
        return '_' + n

    return n


@composite
def MatchValue(draw) -> ast.MatchValue:
    return ast.MatchValue(ast.Constant(0))


@composite
def MatchSingleton(draw) -> ast.MatchSingleton:
    return ast.MatchSingleton(draw(sampled_from([None, True, False])))


@composite
def MatchStar(draw) -> ast.MatchStar:
    return ast.MatchStar(name=draw(sampled_from([None, 'rest'])))


@composite
def MatchSequence(draw, pattern) -> ast.MatchSequence:
    patterns = draw(lists(pattern, min_size=1, max_size=3))

    has_star = draw(booleans())

    if has_star:
        star_pos = draw(integers(min_value=0, max_value=len(patterns)))
        patterns.insert(star_pos, draw(MatchStar()))

    return ast.MatchSequence(patterns=patterns)


@composite
def MatchMapping(draw, pattern) -> ast.MatchMapping:
    patterns = draw(lists(pattern, min_size=1, max_size=3))

    match_mapping = ast.MatchMapping(keys=[ast.Constant(value=0) for i in range(len(patterns))], patterns=patterns)

    has_star = draw(booleans())
    if has_star:
        match_mapping.rest = 'rest'

    return match_mapping


@composite
def MatchClass(draw, pattern) -> ast.MatchClass:
    patterns = draw(lists(pattern, min_size=0, max_size=3))

    kwd_patterns = draw(lists(pattern, min_size=0, max_size=3))
    kwd = ['a' for i in range(len(kwd_patterns))]

    return ast.MatchClass(
        cls=ast.Name(draw(name()), ctx=ast.Load()),
        patterns=patterns,
        kwd_attrs=kwd,
        kwd_patterns=kwd_patterns
    )


@composite
def MatchAs(draw, pattern) -> ast.MatchAs:
    n = draw(one_of(none(), name()))

    if n is None:
        p = None
    else:
        p = draw(pattern)

    return ast.MatchAs(pattern=p, name=n)


@composite
def MatchOr(draw, pattern) -> ast.MatchOr:
    patterns = draw(lists(pattern, min_size=2, max_size=3))
    return ast.MatchOr(patterns=patterns)


leaves = one_of(
    MatchValue(),
    MatchSingleton()
)


def pattern():
    return recursive(
        leaves,
        lambda pattern:
        one_of(
            MatchAs(pattern),        # Simplest - just name binding
            MatchSequence(pattern),   # Simple sequence patterns
            MatchOr(pattern),         # Alternative patterns
            MatchMapping(pattern),    # Dictionary-like patterns
            MatchClass(pattern)       # Most complex - class patterns
        ),
        max_leaves=50
    )


@composite
def Pattern(draw):
    """ A Match case pattern """
    return draw(pattern())
