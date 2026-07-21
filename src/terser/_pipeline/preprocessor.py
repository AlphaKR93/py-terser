import re
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Final


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

    # Directive evaluation
    output = []
    stack: list[tuple[bool, bool | None]] = []
    keeping = lambda: all(s[0] for s in stack)

    for line in lines:
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
