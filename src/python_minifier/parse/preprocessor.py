import re
from python_minifier.config import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


__DIRECTIVES = {
    "if": {
        True: re.compile(r"^#\s?if ([A-Za-z_][A-Za-z0-9_]*)$"),
        False: re.compile(r"^#\s*if\s+([A-Za-z_][A-Za-z0-9_]*)$")
    },
    "elif": {
        True: re.compile(r"^#\s?elif ([A-Za-z_][A-Za-z0-9_]*)$"),
        False: re.compile(r"^#\s*elif\s+([A-Za-z_][A-Za-z0-9_]*)$")
    },
    "else": {
        True: re.compile(r"^#\s?else$#"),
        False: re.compile(r"^#\s*else$#")
    },
    "endif": {
        True: re.compile(r"^#\s?endif$#"),
        False: re.compile(r"^#\s*endif$#")
    },
    "inline": {
        True: re.compile(r"\s*#\s?if ([A-Za-z_][A-Za-z0-9_]*)$"),
        False: re.compile(r"\s*#\s*if\s+([A-Za-z_][A-Za-z0-9_]*)$")
    },
}

def preprocess(source: str, defines: Mapping[str, bool] | None, strict: bool = False) -> tuple[str, str | None]:
    lines = source.splitlines()
    if not lines:
        return "", None

    shebang = lines.pop(0) if lines[0].startswith("#!") else None
    if not defines:
        return source, None

    # Directive evaluation
    output = []
    stack: list[tuple[bool, bool | None]] = []
    keeping = lambda: all(state[0] for state in stack)

    for line in lines:
        stripped = line.strip()

        # Check block directives
        if stripped.startswith('#'):
            if match := __DIRECTIVES["if"][strict].match(stripped):
                defined = defines.get(match.group(1), True)
                parent = all(state[0] for state in stack)
                stack.append((bool(defined) and parent, defined))
            elif match := __DIRECTIVES["elif"][strict].match(stripped):
                if not stack:
                    continue

                defined = defines.get(match.group(1), True)
                parent = all(state[0] for state in stack[:-1])
                _, chosen = stack.pop()
                stack.append((parent and not chosen and bool(defined), defined))
            elif __DIRECTIVES["else"][strict].match(stripped):
                if not stack:
                    continue

                parent = all(state[0] for state in stack[:-1])
                _, chosen = stack.pop()
                stack.append((parent and not chosen, True))
            elif __DIRECTIVES["endif"][strict].match(stripped):
                if stack:
                    stack.pop()
            continue

        # Check inline directive
        if match := __DIRECTIVES["inline"][strict].search(stripped):
            if keeping() and defines.get(match.group(1), True):
                output.append(line[:match.start()])
            continue
        elif keeping():
            output.append(line)

    return '\n'.join(output), shebang
