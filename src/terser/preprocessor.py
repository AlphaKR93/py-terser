import re
from pathlib import Path
from dataclasses import dataclass
from terser.config import TerserConfig

@dataclass
class PreprocessResult:
    path: Path | None
    source: str
    shebang: str | None

class Preprocessor:
    def __init__(self, config: TerserConfig):
        self.config = config

    def preprocess(self, source: str | bytes | None = None, path: Path | str | None = None) -> PreprocessResult:
        resolved_path = None
        if path is not None:
            resolved_path = Path(path).resolve()
            if source is None:
                source = resolved_path.read_bytes()

        if source is None:
            raise ValueError("Either source or path must be provided.")

        if isinstance(source, bytes):
            source_str = source.decode("utf-8")
        else:
            source_str = source

        # Shebang handling on the first line
        shebang = None
        lines = source_str.splitlines()

        if lines and lines[0].startswith("#!"):
            shebang = lines[0]
            lines[0] = ""

        # Directive evaluation
        defines = self.config.defines or {}
        output_lines = []
        stack = []

        def currently_keeping():
            return all(state[0] for state in stack)

        for line in lines:
            stripped = line.strip()

            # Check block directives
            if re.match(r'^#\s*if\s+(\w+)\s*$', stripped):
                cond = re.match(r'^#\s*if\s+(\w+)\s*$', stripped).group(1)
                parent_ok = currently_keeping()
                is_defined = defines.get(cond, False)
                stack.append((parent_ok and is_defined, is_defined))
                output_lines.append('')
                continue
            elif re.match(r'^#\s*else\s*$', stripped):
                if not stack:
                    output_lines.append(line)
                    continue
                parent_ok = all(state[0] for state in stack[:-1])
                prev_keep, prev_chosen = stack.pop()
                stack.append((parent_ok and not prev_chosen, True))
                output_lines.append('')
                continue
            elif re.match(r'^#\s*endif\s*$', stripped):
                if not stack:
                    output_lines.append(line)
                    continue
                stack.pop()
                output_lines.append('')
                continue

            # Check inline directive
            inline_match = re.search(r'\s*#\s*if\s+(\w+)\s*$', line)
            if inline_match:
                cond = inline_match.group(1)
                code_part = line[:inline_match.start()]
                is_defined = defines.get(cond, False)
                if currently_keeping() and is_defined:
                    output_lines.append(code_part)
                else:
                    output_lines.append('')
            else:
                if currently_keeping():
                    output_lines.append(line)
                else:
                    output_lines.append('')

        processed_source = '\n'.join(output_lines)
        return PreprocessResult(resolved_path, processed_source, shebang)
