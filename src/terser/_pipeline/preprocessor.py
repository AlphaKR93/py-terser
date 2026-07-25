import io
import re
import tokenize
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Final


_STRING_TOKEN_TYPES: Final[frozenset[int]] = frozenset(
    {tokenize.STRING}
    | ({tokenize.FSTRING_START, tokenize.FSTRING_MIDDLE, tokenize.FSTRING_END} if hasattr(tokenize, "FSTRING_START") else set())
)


def _multiline_string_body_lines(source: str) -> frozenset[int]:
    """
    1-indexed source line numbers that fall inside the body of a multi-line
    string/f-string literal (its opening line is excluded, since that line may
    have real code before the string starts).

    Directive/comment handling in `preprocess` works line-by-line on raw text
    with no awareness of string literals - without this, a multi-line string
    whose content happens to contain lines starting with `#` (e.g. a string
    constant full of example Python source, itself full of real comments) gets
    its "comment" lines silently dropped, corrupting the string.
    """
    body_lines: set[int] = set()

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type in _STRING_TOKEN_TYPES and tok.start[0] != tok.end[0]:
                body_lines.update(range(tok.start[0] + 1, tok.end[0] + 1))
    except (tokenize.TokenError, SyntaxError):
        # if the source doesn't even tokenize, let the later real parse step
        # raise a proper error - here, just fall back to the old unaware behavior
        return frozenset()

    return frozenset(body_lines)


__DIRECTIVES: Final[Mapping[str, Mapping[bool, re.Pattern]]] = {
    "if": {
        True: re.compile(r"^#\s?if ([A-Za-z_][A-Za-z0-9_]*)$"),
        False: re.compile(r"^#\s*if\s+([A-Za-z_][A-Za-z0-9_]*)$")
    },
    "elif": {
        True: re.compile(r"^#\s?elif ([A-Za-z_][A-Za-z0-9_]*)$"),
        False: re.compile(r"^#\s*elif\s+([A-Za-z_][A-Za-z0-9_]*)$")
    },
    "else": {
        True: re.compile(r"^#\s?else$"),
        False: re.compile(r"^#\s*else$")
    },
    "endif": {
        True: re.compile(r"^#\s?endif$"),
        False: re.compile(r"^#\s*endif$")
    },
}

__INLINE_DIRECTIVE: Final[Mapping[bool, re.Pattern]] = {
    True: re.compile(r"\s*#\s?if ([A-Za-z_][A-Za-z0-9_]*)$"),
    False: re.compile(r"\s*#\s*if\s+([A-Za-z_][A-Za-z0-9_]*)$")
}

def preprocess(source: str, defines: Mapping[str, bool] | None, strict: bool = False) -> tuple[str, str | None]:
    lines = source.splitlines()
    if not lines:
        return "", None

    shebang = lines.pop(0) if lines[0].startswith("#!") else None
    defines: Mapping[str, bool] = defines or {}

    string_body_lines = _multiline_string_body_lines(source)
    line_offset = 2 if shebang is not None else 1

    # Directive evaluation
    output = []
    stack: list[tuple[bool, bool | None]] = []
    keeping = lambda: all(s[0] for s in stack)

    for i, line in enumerate(lines):
        if (i + line_offset) in string_body_lines:
            # inside the body of a multi-line string/f-string - pass through
            # untouched, whatever it looks like isn't a real comment/directive
            output.append(line)
            continue

        stripped = line.strip()

        if not stripped.startswith('#'):
            if not (match := __INLINE_DIRECTIVE[strict].search(stripped)):
                output.append(line)
            elif defines.get(match.group(1), True) and keeping():
                output.append(line[:match.start()])
            continue

        # Check block directives
        if match := __DIRECTIVES["if"][strict].match(stripped):
            defined: bool = defines.get(match.group(1), True)
            stack.append((defined and keeping(), defined))
        elif match := __DIRECTIVES["elif"][strict].match(stripped):
            if not stack:
                continue

            defined: bool = defines.get(match.group(1), True)
            _, before = stack.pop()
            stack.append((defined and not before and keeping(), defined))
        elif __DIRECTIVES["else"][strict].match(stripped):
            if not stack:
                continue

            _, before = stack.pop()
            stack.append((not before and keeping(), True))
        elif __DIRECTIVES["endif"][strict].match(stripped):
            if stack:
                stack.pop()

    return '\n'.join(output), shebang
