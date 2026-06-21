# `py-terser` Inplementation Plan

Target: Python ≥ 3.10 (Vercel Functions, Serverless, FastAPI & FastMCP).

---

## Philosophy

- **Preprocess-first.** File I/O, shebang handling, and directive evaluation happen before any AST work.
- **AST-driven.** All structural decisions use AST nodes. No string/regex on code structure, decorator names, base classes, or imports.
- **No transform in printer.** `Printer` emits code only; zero transformation logic.
- **Multi-threaded.** Preprocess and Parse run concurrently across files (configurable thread count).
- **No unnecessary abstraction.** Single-use code stays inline. Shared logic (e.g., constant evaluation) is abstracted.

---

## Pipeline

```
Files
  |
  v
[0] Preprocess   --- parallel (ThreadPoolExecutor, N threads)
      Resolve path, read bytes, strip/save shebang,
      evaluate #if/#endif directives -> source str
  |
  v
[1] Parse        --- parallel (same pool)
      ast.parse -> Module AST
      Apply early transforms: FoldConstants (__debug__ -> False),
      RemoveDeadBlocks (statically-resolved branches)
  |
  v
[2] Link        --- sequential
      Resolve names from parsed ASTs, bind scopes, link cross-module imports
      add_parent, add_namespace, bind_names, resolve_names
  |
  v
[3] Transform    --- parallel, repeated M times (configurable)
      Apply all transform passes in fixed order (see Transforms section)
      Remove __all__ once after final pass
  |
  v
[4] Mangle       --- sequential
      Name mangling (formerly obfuscation):
      rename locals/globals, hoist literals, alias frequent names,
      update dynamic imports
  |
  v
[5] Print        --- parallel
      Unparse AST -> source str, restore shebang
      Emit obfuscation map if requested
```

---

## Architecture

### Module Layout

```
src/terser/
  pipeline.py          # Orchestrates all stages; public entry point
  config.py            # TerserConfig dataclass (all options)
  preprocessor.py      # Stage 0: path resolution, file I/O, shebang, directives
  parser.py            # Stage 1: ast.parse + early transforms (FoldConstants, RemoveDeadBlocks)
  linker.py            # Stage 2: name binding, scope resolution, cross-module linking
  mangler.py           # Stage 4: rename, literal hoisting, dynamic import update
  printer/             # Stage 5: AST -> source (no transforms)
  transforms/          # Stage 3 passes (one file per pass)
    runner.py          # TransformRunner: applies passes in order, repeated N times
  rename/              # Name binding/resolution utilities (used by linker + mangler)
  _ast/                # AST utilities (compat, parent annotation, compare)
  hints.py             # terser.hints decorators/markers (preserve_typing, inline, etc.)
```

### `TerserConfig`

All options in one dataclass. Passed through pipeline stages.

```python
@dataclass
class TerserConfig:
    # Threading
    threads: int = 4
    transform_passes: int = 3          # how many times Transform stage repeats

    # Pipeline toggles
    fold_constants: bool = True
    optimize: bool = True              # remove-asserts + remove-debug merged
    defines: dict[str, bool] = field(default_factory=dict)

    # Transform toggles (all True by default unless noted)
    remove_docstrings: bool = True
    strict_docstrings: bool = True     # preserve module-level docstrings
    remove_annotations: bool = True
    remove_explicit_inherits: bool = True  # RemoveExplicitInherits (formerly remove_object_base)
    remove_type_stmt: bool = True
    remove_trailing_returns: bool = True
    simplify_posargs: bool = True
    simplify_dynamic_attrs: bool = True
    simplify_fstring: bool = True
    simplify_early_exit: bool = True
    simplify_raise: bool = True
    simplify_if_stmt: bool = True
    convert_to_ternary: bool = True
    convert_to_lambda: bool = True
    hoist_literals: bool = True
    inline_functions: bool = True
    inline_int_flags: bool = True
    cleanup_imports: bool = True

    # Mangle
    rename_locals: bool = True
    rename_globals: bool = False
    preserve_locals: list[str] = field(default_factory=list)
    # preserve_globals: list of names to exclude from renaming.
    # Each entry is either:
    #   "name"        -- preserve in all modules
    #   "mod:name"    -- preserve only when current_module_name == "mod"
    # CLI parses comma-separated values; "mod:name" entries are filtered
    # at mangle time against current_module_name.
    preserve_globals: list[str] = field(default_factory=list)
    ignore_all: bool = False

    # Output
    prefer_single_line: bool = True
    preserve_shebang: bool = True
    # obfuscation_map: OUTPUT. Pass an empty dict; Mangler populates it with
    #   {original_name: mangled_name} for every renamed binding.
    #   Used by CLI to write the JSON obfuscation map file.
    obfuscation_map: dict | None = None
    # rename_map: INPUT. Maps original string literals in dynamic import calls
    #   (__import__("x"), importlib.import_module("x")) to their new names.
    #   Populated from module_name_map after mangling; passed to DynamicImportRenamer.
    rename_map: dict | None = None

    # Cross-module obfuscation
    # module_name_map: maps each component name (package/module segment) to its
    #   mangled short name, e.g. {"myapp": "a", "utils": "b"}.
    #   Built by CLI from all module path components before processing starts.
    #   Used by ModuleObfuscator (Stage 2) and path renaming (Stage 5 output).
    module_name_map: dict | None = None
    # current_module_name: dotted module name of the file being processed,
    #   e.g. "myapp.routers.users". Derived from filename if not provided.
    #   Used by ModuleObfuscator for relative import resolution and
    #   preserve_globals "mod:name" filtering.
    current_module_name: str | None = None
    # user_modules: set of all user-defined dotted module names in the project,
    #   e.g. {"myapp", "myapp.utils", "myapp.routers"}.
    #   Used by ModuleObfuscator to distinguish user imports (rewrite)
    #   from stdlib/third-party imports (leave alone).
    user_modules: set[str] = field(default_factory=set)

    # sys constants for EnvironmentConstantTransformer
    version_info: tuple = (3, 10, 0)
    platform: str = 'linux'
```

### `Pipeline`

```python
class Pipeline:
    def __init__(self, config: TerserConfig): ...
    def run(self, paths: list[str | Path]) -> list[MinifiedResult]: ...
    def run_source(self, source: str, filename: str) -> MinifiedResult: ...
```

Stages 0 and 1 use `concurrent.futures.ThreadPoolExecutor(max_workers=config.threads)`.
Stage 3 loops `config.transform_passes` times.

### `TransformPass` Protocol

```python
class TransformPass(Protocol):
    def __call__(self, module: ast.Module) -> ast.Module: ...
```

Each pass is a callable class in `transforms/`. `TransformRunner` applies them in order.

---

## Stage 0 — Preprocess

**Module:** `preprocessor.py`
**Class:** `Preprocessor`

1. Resolve absolute path.
2. Read bytes → decode UTF-8.
3. Extract and strip shebang (first line `#!...`). Store in `PreprocessResult.shebang`.
4. Evaluate `#if DEFINE` / `#else` / `#endif` directives against `config.defines`.
   - Block and inline forms both supported.
   - Replaced with empty lines (preserve line numbers for error messages).
5. Return `PreprocessResult(path, source, shebang)`.

```python
@dataclass
class PreprocessResult:
    path: Path
    source: str
    shebang: str | None
```

---

## Stage 1 — Parse

**Module:** `parser.py`
**Class:** `Parser`

1. `ast.parse(source, filename)`.
2. `add_parent(module)`.
3. If `config.fold_constants`: apply early `FoldConstants` subset:
   - `__debug__` → `False`, `typing.TYPE_CHECKING` → `False`.
   - `sys.version_info` / `sys.platform` substitution.
   - Constant expression folding.
4. `RemoveDeadBlocks` (statically-resolved `if True/False` branches).
5. Return `ParseResult(module)`.

Early transforms in Parse are a **subset** of full `FoldConstants`. Full `FoldConstants` re-runs in the Transform stage.

---

## Stage 2 — Link

**Module:** `linker.py`
**Class:** `Linker`

1. `add_namespace(module)`.
2. `bind_names(module)`.
3. `resolve_names(module)`.
4. Cross-module: if `config.module_name_map`, run `ModuleObfuscator` to update import references.
5. Attach resolved scope info to module for use by transforms.

---

## Stage 3 — Transform

**Module:** `transforms/runner.py`
**Class:** `TransformRunner`

Runs all enabled passes in fixed order, repeated `config.transform_passes` times.
After the **final** pass iteration: remove `__all__` assignment from `module.body`.

`add_parent` + `add_namespace` called before each full pass cycle (not between individual passes unless a pass explicitly requires it — documented per pass).

### Transform Pass Order

| # | Class | File |
|---|-------|------|
| 1 | `FoldConstants` | `constant_folding.py` |
| 2 | `Contracts` | `contracts.py` |
| 3 | `InlineLambdaInvoke` | `inline_lambda_invoke.py` |
| 4 | `RemoveDummyVariables` | `remove_dummy_variables.py` |
| 5 | `RemoveExplicitFields` | `remove_explicit_fields.py` |
| 6 | `RemoveDeadBlocks` | `remove_dead_blocks.py` |
| 7 | `RemoveDocstrings` | `remove_docstrings.py` |
| 8 | `RemoveOverloads` | `remove_overloads.py` |
| 9 | `RemoveExplicitInherits` | `remove_explicit_inherits.py` |
| 10 | `RemoveBareProtocols` | `remove_bare_protocols.py` |
| 11 | `RemoveGenerics` | `remove_generics.py` |
| 12 | `RemoveAnnotations` | `remove_annotations.py` |
| 13 | `RemoveAsserts` | `remove_asserts.py` |
| 14 | `RemoveTypeStmt` | `remove_type_stmt.py` |
| 15 | `RemoveTrailingReturns` | `remove_trailing_returns.py` |
| 16 | `SimplifyPositionArguments` | `simplify_posargs.py` |
| 17 | `SimplifyDynamicAttributes` | `simplify_dynamic_attrs.py` |
| 18 | `SimplifyFString` | `simplify_fstring.py` |
| 19 | `SimplifyEarlyExit` | `simplify_early_exit.py` |
| 20 | `SimplifyRaise` | `simplify_raise.py` |
| 21 | `SimplifyIfStmt` | `simplify_if_stmt.py` |
| 22 | `ConvertToTernary` | `convert_to_ternary.py` |
| 23 | `ConvertToLambda` | `convert_to_lambda.py` |
| 24 | `HoistLiterals` | `hoist_literals.py` |
| 25 | `RemovePass` | `remove_pass.py` |
| 26 | `RemoveTypingDecorators` | `remove_typing_decorators.py` |
| 27 | `InlineFunctions` | `inline_functions.py` |
| 28 | `InlineIntFlags` | `inline_int_flags.py` |
| 29 | `CleanupImports` | `cleanup_imports.py` |
| — | `__all__` removal | (in TransformRunner, after final cycle) |

---

## Transform Pass Specifications

### 1. `FoldConstants`

Sub-transformers applied in sequence within one pass, sharing `ConstantTransformerBase`:

| Sub-transformer | Action |
|-----------------|--------|
| `DebugConstantTransformer` | `__debug__` → `False`, `typing.TYPE_CHECKING` → `False` |
| `NumberRepresentationOptimizer` | Shortest repr: `0b1` → `1`, `1000000` → `1e6`, `0.0001` → `1e-4` |
| `EnvironmentConstantTransformer` | `sys.version_info` → config value, `sys.platform` → config value |
| `ExpressionFolder` | Fold math/unary/binary ops on constant operands |
| `UnicodeEscapeExpander` | `\uXXXX` / `\UXXXXXXXX` → raw UTF-8 in str/bytes literals |
| `CollectionLiteralFolder` | `list()` → `[]`, `dict()` → `{}`, `tuple()` → `()`, `set([1,2])` → `{1,2}` if shorter |
| `BooleanSimplifier` | `not x is None` → `x is not None`, `x == True` → `x`, `x == False` → `not x` |

`ConstantTransformerBase`: abstract visitor with helpers for expression evaluation, round-trip verification, and node replacement.

---

### 2. `Contracts`

Removes contract-related call nodes. **No decorator handling** (decorator patterns handled by `InlineLambdaInvoke`).

- `typing.cast(Type, value)` → `value`.
- `terser.hints.unreachable()` call statements → remove.
- `typing.assert_never(x)` call statements → remove.
- `typing.assert_type(x, T)` call statements → remove.

---

### 3. `InlineLambdaInvoke`

Inlines `@lambda _: _()` wrapper pattern. Only when the wrapped function body has **no `nonlocal` statements**.

- Strip the outer decorator.
- Hoist inner function body to the enclosing scope inline.

Covers:
- Decorator form: `@lambda _: _()\ndef foo(): ...`
- Direct IIFE: `(lambda: body)()` — if body contains no `nonlocal`.

---

### 4. `RemoveDummyVariables`

Merged T19 (dead store eliminator) + T20 (unused exception name pruner).

**Dummy variable removal (all-underscore names):**
- Names composed entirely of `_` (e.g., `_`, `__`, `___`) are always dead stores.
- If any all-underscore name is referenced after assignment: `raise` + stop.
- Exception: lambda params / single-expression function params → warning + skip (not raise).

**Dead assignment removal:**
- Assignment target never read after assignment → remove.
- If RHS is a literal (`None`, int, float, str, bool, `...`) → remove entire statement.
- If RHS has possible side effects → replace with bare expression (`_ = call()` → `call()`).
- **Assignment only removed.** Value is not propagated/inlined (handled by `HoistLiterals` / `FoldConstants`).

**Unused exception name:**
- `except Exc as e:` where `e` never referenced in the handler body → `except Exc:`.

---

### 5. `RemoveExplicitFields`

Same skip conditions as `RemoveAnnotations` (see pass 12).

Removes annotation-only field declarations with no default value, not `ClassVar`, no metaclass requirement:

```python
class Foo:
    foo: str        # removed (annotation-only, no default)
    bar: int = 0    # kept (has default)
```

If class body becomes empty after removal, insert `pass` (cleaned up by `RemovePass` later).

---

### 6. `RemoveDeadBlocks`

- `if True [or ...]: body [elif/else: ...]` → inline `body`, discard branches.
- `if False [and ...]: ...` → keep remaining branches (`elif` promoted to `if`, lone `else` inlined), or remove if none remain.
- `(if|with|for|while|try): pass` only → remove.
  - **Walrus operator:** if condition contains `:=`, convert walrus to standalone assignment; do not remove.
  - **Side-effect guard on `for`:** `for x in foo` where `foo` is not a known literal/builtin and `foo` is referenced after the loop → skip.
- Recurse into nested blocks.

---

### 7. `RemoveDocstrings`

- Remove docstrings from modules, classes, functions.
- Non-docstring literal expressions (e.g., standalone string mid-function) preserved.
- `@terser.hints.preserve_docstring` → preserve that scope's docstring.
- `config.strict_docstrings=True` (default): preserve module-level docstring.
- `config.strict_docstrings=False`: always strip module-level docstring.

---

### 8. `RemoveOverloads`

- Collect all same-name function defs within a scope.
- Remove all `@typing.overload` / `@overload` variants.
- Keep the single non-overload implementation.

Error conditions (raise + stop):
- No non-overload implementation exists (excluding `@abstractmethod`).
- Two or more non-overload implementations exist.

---

### 9. `RemoveExplicitInherits`

Replaces old `RemoveObject`. Folds known redundant base/metaclass patterns.

- `class Foo(object)` → `class Foo`.
- `class Foo(object, X)` → `class Foo(X)` (remove `object` from bases).
- `class Bar(metaclass=ABCMeta)` → `class Bar(ABC)`.
  - Validate `from abc import ABC` is present; add import if missing.
  - Validate `ABCMeta` import is now unused; remove if so.

---

### 10. `RemoveBareProtocols`

- Remove `class Foo(Protocol): ...` definitions not decorated with `@typing.runtime_checkable`.
- Remove all usage as a base class (type annotations already stripped by `RemoveAnnotations`).
- Skip if `@typing.runtime_checkable` present.

---

### 11. `RemoveGenerics`

- Remove `typing.TypeVar(...)`, `typing.ParamSpec(...)`, `typing.TypeVarTuple(...)` assignment statements.
- Remove `typing.Generic` from base class lists.
- Remove PEP 695 generic brackets: `class Foo[T]:` → `class Foo:`, `def foo[T]():` → `def foo():`.

---

### 12. `RemoveAnnotations`

Merged `RemoveAnnotations` + `RemoveTypeHints`. Single pass for all annotation removal.

**Skip conditions (preserve annotation):**
- `typing.Annotated[..., ...]` usage → skip entire annotation.
- `@terser.hints.preserve_typing` on the class/function → skip.

**Field-level skip (class fields only):**
- Class inherits `pydantic.BaseModel` → skip field annotations; process method annotations normally.
- Class decorated `@dataclasses.dataclass` → skip field annotations; process method annotations normally.

**Always remove, regardless of skip conditions:**
- `@typing.no_type_check` / `@typing.no_type_check_decorator` (pre-3.15) on a function → remove all annotations for that function.
  - If applied to a `BaseModel` or `dataclass` class → `raise` + stop.
- Literal (string-form) type annotations (`foo: "Foo"`, `def bar() → "Baz"`) → always remove.
  - If in a `BaseModel` or `dataclass` field → `raise` + stop.
- Annotation-only statement for an already-declared variable (prior `foo = ...` exists, subsequent `foo: Foo` has no value store) → always remove.
- Function return annotations and argument annotations (subject to above skip conditions).

---

### 13. `RemoveAsserts`

- Remove `assert` statements.
- Enabled when `config.optimize=True` (merged `--remove-debug` + `--remove-asserts` CLI flags).

---

### 14. `RemoveTypeStmt`

- Remove PEP 695 `type X = ...` statements.
- These are dead after `RemoveAnnotations` strips annotation usage.

---

### 15. `RemoveTrailingReturns`

- Remove trailing `return None` or bare `return` at the end of a function body.

---

### 16. `SimplifyPositionArguments`

- `def foo(a, /, b)` → `def foo(a, b)`.
- Removes positional-only separator `/`.

---

### 17. `SimplifyDynamicAttributes`

**Conversions:**
- `getattr(obj, "foo")` → `obj.foo`.
- `setattr(obj, "foo", val)` → `obj.foo = val`.
- `Clazz.__getattr__(obj, "foo")` → `obj.foo` only if `obj` is statically known to be `Clazz` and `Clazz` does not override `__getattr__`.
- Same rules apply for `__setattr__`.

**Skip conditions:**
- 3-arg `getattr(obj, "foo", default)` → skip.
- Attribute name starts with `__` → skip (name mangling).
- Attribute name is not a valid Python identifier → skip.

---

### 18. `SimplifyFString`

- `f"{x}"` → `str(x)`, or `x` if `x` is statically `str`.
- `f"{x}{y}"` → `x + y` only if both are statically `str`.
- Literal parts hoisted/merged where possible.
- Only applied if result is shorter or equal in byte count.

---

### 19. `SimplifyEarlyExit`

- `else` / `elif` block following a definite early exit (`return`, `raise`, `continue`, `break`) in the preceding `if` branch → remove `else`, dedent body into parent scope.

---

### 20. `SimplifyRaise`

- `raise TypeError()` → `raise TypeError` (drop no-arg call).
- Only for built-in exception types with no arguments.

---

### 21. `SimplifyIfStmt`

- Single-expression `if` with no `else`:
  ```python
  if cond:
      func(x)
  ```
  → `cond and func(x)` as `ast.Expr`.
- Only when body is a single expression statement.

---

### 22. `ConvertToTernary`

- `if cond: return a\nelse: return b` → `return a if cond else b`.
- `if cond: return a\nreturn b` → `return a if cond else b` (no explicit `else` needed).
- Assignment form:
  ```python
  if fizz: foo = a
  elif buzz: foo = b
  else: foo = c
  ```
  → `foo = a if fizz else b if buzz else c`.
  - All branches must assign to the **same target** with the **same operator** (all `=`, or all `+=`, etc.; mixing forbidden).

---

### 23. `ConvertToLambda`

- `def foo(args): return expr` → `foo = lambda args: expr`.
- Conditions: single-expression body (or compressible to one), no docstring.
- Decorators handled: `@dec\ndef foo(): expr` → `foo = dec(lambda: expr)`.

---

### 24. `HoistLiterals`

- Short literal constants referenced once or twice → inline at use site when propagation + deletion yields fewer bytes.
- Only for literals (int, float, str, bool, `None`, `...`).

---

### 25. `RemovePass`

- Remove `pass` from non-empty suites.
- Runs after all other passes to clean up any empty suites created during transformation.

---

### 26. `RemoveTypingDecorators`

Removes no-op typing/hint decorators:

- `@terser.hints.*` (any hint decorator).
- `@typing.override`.
- `@typing.final`.
- Additional decorators configurable via `config`.

---

### 27. `InlineFunctions`

Inline a function at all call sites when **any** condition holds:

- Body is a lambda or single expression (or compressible to one).
- Module-private (`__`-prefixed name) **and** used exactly once.
- Used only within the module (not exported) **and** used exactly once.
- Decorated with `@terser.hints.inline`.

Remove original function definition after inlining.

---

### 28. `InlineIntFlags`

Inline `enum.IntFlag` subclasses: replace member references with raw integers, delete class definition.

**Conditions to inline (any one):**
- Defined inline (inside a function or as a nested class).
- Module-private (used only within module, or `__`-prefixed name). Count-independent.
- Decorated with `@terser.hints.inline`.

**Requirements:**
- Must inherit **only** `enum.IntFlag` (no other bases).
- Must have **no methods**.
- If `@terser.hints.inline` but has other bases or methods → `raise` + stop.

---

### 29. `CleanupImports`

Merged `CombineImports` + unused import removal.

- Combine `import` statements for the same module: `import a; import b` → `import a, b`.
- Combine `from X import a; from X import b` → `from X import a, b`.
- Remove imports where the imported name is never referenced in the module.
- Module-wide scope: names in `__all__` are treated as referenced (preserved).
- Scope-aware for local imports: function-local imports only removed if unused within that function's scope.

---

### `__all__` Removal

After the **final** Transform pass iteration, `TransformRunner` removes the `__all__` assignment:

```python
module.body = [
    s for s in module.body
    if not (
        isinstance(s, ast.Assign)
        and len(s.targets) == 1
        and isinstance(s.targets[0], ast.Name)
        and s.targets[0].id == '__all__'
    )
]
```

---

## Stage 4 — Mangle

**Module:** `mangler.py`
**Class:** `Mangler`

1. Filter `preserve_globals`: module-qualified entries (`"mod:name"`) resolved against `config.current_module_name`.
2. `allow_rename_locals` / `allow_rename_globals` per config.
3. `rename_literals` if `config.hoist_literals`.
4. `rename(module)` — assign short mangled names.
5. `LocalReferenceAliaser` — frequently-referenced globals aliased to short locals.
6. `DynamicImportRenamer` — update `__import__("x")` / `importlib.import_module("x")` string args to mangled names.
7. Populate `config.obfuscation_map` if provided.

---

## Stage 5 — Print

**Module:** `printer/`
**Class:** `ModulePrinter`

- Unparse AST → source string. **No transforms.**
- Re-parse output + `compare_ast` for stability check.
  - Mismatch → raise `UnstableMinification`.
- Prepend shebang if `config.preserve_shebang` and shebang was found in Stage 0.

---

## CLI Mapping

All CLI flags map 1:1 to `TerserConfig` fields. Flags are `--no-*` for fields that default to `True`, and plain `--*` for fields that default to `False`.

### I/O

| Flag | Config field | Default |
|------|--------------|---------|
| `path` (positional) | *(pipeline input)* | required |
| `--output / -o` | *(pipeline output path)* | stdout |
| `--in-place / -i` | *(pipeline output mode)* | false |
| `--obfuscation-map FILE` | `obfuscation_map` (output path) | None |
| `--prefer-single-line` | `prefer_single_line` | False |
| `--no-preserve-shebang` | `preserve_shebang=False` | True |

### Threading & Passes

| Flag | Config field | Default |
|------|--------------|---------|
| `--threads N` | `threads` | 4 |
| `--transform-passes N` | `transform_passes` | 1 |

### Pipeline

| Flag | Config field | Default |
|------|--------------|---------|
| `--no-constant-folding` | `fold_constants=False` | True |
| `--optimize` | `optimize=True` | False |
| `--define NAME[=1\|0]` | `defines` | {} |

### Transforms

| Flag | Config field | Default |
|------|--------------|---------|
| `--remove-literal-statements` | `remove_docstrings=True` | False |
| `--no-strict-docstrings` | `strict_docstrings=False` | True |
| `--no-remove-annotations` | `remove_annotations=False` | True |
| `--no-remove-object-base` | `remove_explicit_inherits=False` | True |
| `--no-remove-type-stmt` | `remove_type_stmt=False` | True |
| `--no-remove-explicit-return-none` | `remove_trailing_returns=False` | True |
| `--no-convert-posargs-to-args` | `simplify_posargs=False` | True |
| `--no-simplify-dynamic-attrs` | `simplify_dynamic_attrs=False` | True |
| `--no-simplify-fstring` | `simplify_fstring=False` | True |
| `--no-simplify-early-exit` | `simplify_early_exit=False` | True |
| `--no-remove-builtin-exception-brackets` | `simplify_raise=False` | True |
| `--no-simplify-if-stmt` | `simplify_if_stmt=False` | True |
| `--no-convert-to-ternary` | `convert_to_ternary=False` | True |
| `--no-convert-to-lambda` | `convert_to_lambda=False` | True |
| `--no-hoist-literals` | `hoist_literals=False` | True |
| `--no-inline-functions` | `inline_functions=False` | True |
| `--no-inline-int-flags` | `inline_int_flags=False` | True |
| `--no-combine-imports` | `cleanup_imports=False` | True |

### Mangle

| Flag | Config field | Notes |
|------|--------------|-------|
| `--no-rename-locals` | `rename_locals=False` | |
| `--preserve-locals NAMES` | `preserve_locals` | comma-separated, repeatable |
| `--rename-globals` | `rename_globals=True` | |
| `--preserve-globals NAMES` | `preserve_globals` | comma-separated, repeatable; format: `name` or `mod:name` |
| `--ignore-all` | `ignore_all=True` | |

`preserve_globals` parsing: each `--preserve-globals` value is split on `,`. Entries of the form `mod:name` are filtered at mangle time — only preserved when `current_module_name == mod`. Plain `name` entries are always preserved.

---

## Verification Checklist

### Architecture

- [x] `TerserConfig` is the single source of truth for all options; no flags passed as loose arguments between stages.
- [x] `Pipeline.run()` uses `ThreadPoolExecutor` for stages 0+1; thread count == `config.threads`.
- [x] `Pipeline.run()` runs Transform stage exactly `config.transform_passes` times.
- [x] `TransformRunner` calls `add_parent` + `add_namespace` before each pass cycle, not between individual passes.
- [x] `TransformRunner` removes `__all__` assignment exactly once, after the final pass cycle.
- [x] All 29 transform passes are registered in `TransformRunner` in the documented order.
- [x] Each pass is gated by its corresponding `TerserConfig` bool field; disabled passes are skipped entirely.
- [x] No transform logic exists in `printer/` or `parser.py` beyond the documented early-transform subset.
- [x] `UnstableMinification` is raised on AST round-trip mismatch after printing.
- [x] `preserve_globals` entries in `"mod:name"` form are filtered per `current_module_name` at mangle time only.

### Stage 0 -- Preprocess

- [x] Shebang (first line `#!...`) is stripped from source and stored in `PreprocessResult.shebang`.
- [x] `#if` / `#else` / `#endif` directives are replaced with empty lines (line numbers preserved).
- [x] Inline `# if DEFINE` directives on the same line are handled.
- [x] Undefined `defines` keys evaluate to `False` (not error).
- [x] Non-directive `#` comments pass through unmodified.

### Stage 1 -- Parse

- [x] `ast.parse` failure raises with filename included in error.
- [x] Early `FoldConstants` only runs `__debug__`, `TYPE_CHECKING`, `sys.version_info`, `sys.platform`, and constant expression folding; `CollectionLiteralFolder` / `BooleanSimplifier` do **not** run here.
- [x] Early `RemoveDeadBlocks` runs after early `FoldConstants` (correct order).
- [x] Full `FoldConstants` in Transform stage re-runs all sub-transformers without conflict.

### Stage 2 -- Link

- [x] `add_namespace` → `bind_names` → `resolve_names` called in that order.
- [x] `ModuleObfuscator` only runs when `module_name_map` is non-empty.
- [x] Relative imports are resolved correctly using `current_module_name` and `level`.
- [x] `user_modules` correctly distinguishes user imports from stdlib/third-party.

### Stage 4 -- Mangle

- [x] `preserve_globals` `"mod:name"` entries only preserved when `current_module_name == mod`; plain `"name"` entries always preserved.
- [x] `rename_literals` runs only when `config.hoist_literals=True`.
- [x] `obfuscation_map` dict is populated with `{original_name: mangled_name}` for every renamed binding.
- [x] `rename_map` passed to `DynamicImportRenamer` reflects post-mangle module names from `module_name_map`.
- [x] `module.preserved` names are appended to both `preserve_locals` and `preserve_globals` before renaming.
- [x] `module_name_map` values (obfuscated module names) added to `preserve_globals` to prevent double-mangling.

### Stage 5 -- Print

- [x] Shebang from `PreprocessResult.shebang` is prepended when `config.preserve_shebang=True`.
- [x] Printer emits no transformation logic whatsoever.
- [x] `compare_ast(module, reparsed)` passes; `UnstableMinification` raised on mismatch.

### Pass 1: `FoldConstants`

- [x] `DebugConstantTransformer`: `__debug__` → `False`, `typing.TYPE_CHECKING` → `False`.
- [x] `NumberRepresentationOptimizer`: picks shortest of decimal, hex, binary, scientific notation.
- [x] `EnvironmentConstantTransformer`: replaces `sys.version_info` and `sys.platform` only; does not touch other `sys.*` attributes.
- [x] `ExpressionFolder`: folds only when all operands are constants; does not fold expressions with side effects.
- [x] `UnicodeEscapeExpander`: expands `\uXXXX` / `\UXXXXXXXX`; leaves other escape sequences untouched.
- [x] `CollectionLiteralFolder`: `set([1, 2])` → `{1, 2}` only when result is strictly shorter in bytes.
- [x] `BooleanSimplifier`: does not simplify when operand may have custom `__eq__`.

### Pass 2: `Contracts`

- [x] `typing.cast(T, v)` → `v`; cast node fully removed.
- [x] `terser.hints.unreachable()` / `typing.assert_never(x)` / `typing.assert_type(x, T)` call statements removed.
- [x] Non-statement uses (e.g., `x = typing.cast(T, v)`) handled: assignment RHS replaced with `v`.
- [x] **No** decorator unwrapping in this pass (belongs to `InlineLambdaInvoke`).

### Pass 3: `InlineLambdaInvoke`

- [x] Decorator form `@lambda _: _()` stripped and inner body hoisted.
- [x] Direct IIFE `(lambda: body)()` inlined.
- [x] Skip when wrapped function body contains any `nonlocal` statement.
- [x] Lambda param `_` (single-use dummy) not flagged by `RemoveDummyVariables` for lambda params (warning only).

### Pass 4: `RemoveDummyVariables`

- [x] All-underscore target names (`_`, `__`, `___`, ...) treated as dead stores unconditionally.
- [x] All-underscore names referenced after assignment → `raise` + stop.
- [x] Exception: all-underscore lambda params / single-expression function params → warning + skip.
- [x] Dead assignment (target never read after) with literal RHS → entire statement removed.
- [x] Dead assignment with non-literal RHS → assignment replaced with bare expression (side-effect preserved).
- [x] `except Exc as e:` where `e` unreferenced in handler → `except Exc:`.

### Pass 5: `RemoveExplicitFields`

- [x] Annotation-only field (no value, not `ClassVar`) in a class body is removed.
- [x] Field with default value is preserved.
- [x] `ClassVar`-annotated field is preserved.
- [x] Same skip conditions as `RemoveAnnotations` apply (BaseModel fields, Annotated, etc.).
- [x] Empty class body after removal gets `pass` inserted.

### Pass 6: `RemoveDeadBlocks`

- [x] `if True [or ...]: body` → body inlined, all branches discarded.
- [x] `if False [and ...]: ...` → only remaining branches kept; lone `else` inlined; no branches → statement removed.
- [x] Walrus operator (`:=`) in condition → converted to assignment statement; block not removed.
- [x] `for x in foo: pass` where `foo` is custom iterator and `foo` referenced after → skip.
- [x] `(if|with|while|try): pass` only → removed.
- [x] Recursion into nested blocks.

### Pass 7: `RemoveDocstrings`

- [x] Module, class, and function docstrings removed when `config.remove_docstrings=True`.
- [x] Non-docstring string literals mid-body preserved.
- [x] `@terser.hints.preserve_docstring` preserves that node's docstring.
- [x] `strict_docstrings=True`: module-level docstring preserved.
- [x] `strict_docstrings=False`: module-level docstring removed.

### Pass 8: `RemoveOverloads`

- [x] All `@typing.overload` / `@overload` variants removed.
- [x] Exactly one non-overload implementation kept.
- [x] Zero non-overload implementations (not counting `@abstractmethod`) → `raise` + stop.
- [x] Two or more non-overload implementations → `raise` + stop.

### Pass 9: `RemoveExplicitInherits`

- [x] `class Foo(object)` → `class Foo`.
- [x] `object` removed from multi-base lists: `class Foo(object, Bar)` → `class Foo(Bar)`.
- [x] `class Bar(metaclass=ABCMeta)` → `class Bar(ABC)`.
- [x] `from abc import ABC` added if not already present after ABCMeta fold.
- [x] `ABCMeta` import removed if no longer referenced.

### Pass 10: `RemoveBareProtocols`

- [x] Non-`@runtime_checkable` Protocol subclasses removed entirely.
- [x] `@typing.runtime_checkable` Protocol subclasses preserved.
- [x] All uses as a base class of the removed Protocol are cleaned up.

### Pass 11: `RemoveGenerics`

- [x] `typing.TypeVar(...)`, `typing.ParamSpec(...)`, `typing.TypeVarTuple(...)` assignment statements removed.
- [x] `typing.Generic` removed from base class lists.
- [x] PEP 695 `[T]` / `[T, U]` brackets removed from `ClassDef` and `FunctionDef`.

### Pass 12: `RemoveAnnotations`

- [x] `typing.Annotated[...]` annotation → skip (entire annotation preserved).
- [x] `@terser.hints.preserve_typing` → skip all annotations for that node.
- [x] `BaseModel` field annotations → skip; method annotations processed.
- [x] `@dataclasses.dataclass` field annotations → skip; method annotations processed.
- [x] `@typing.no_type_check` on a function → remove all annotations regardless of BaseModel/dataclass.
- [x] `@typing.no_type_check` on a BaseModel/dataclass class → `raise` + stop.
- [x] String-literal annotation (`foo: "Foo"`, `-> "Bar"`) → always remove.
- [x] String-literal annotation on BaseModel/dataclass field → `raise` + stop.
- [x] Annotation-only re-declaration of already-declared variable → always remove.

### Pass 13: `RemoveAsserts`

- [x] `assert` statements removed when `config.optimize=True`.
- [x] `assert expr, msg` → entire statement removed (not just the message).

### Pass 14: `RemoveTypeStmt`

- [x] PEP 695 `type X = ...` statements removed.
- [x] `type` keyword in expressions (not statements) unaffected.

### Pass 15: `RemoveTrailingReturns`

- [x] Trailing `return None` at function end removed.
- [x] Trailing bare `return` at function end removed.
- [x] Non-trailing returns left untouched.

### Pass 16: `SimplifyPositionArguments`

- [x] `/` separator removed from function signatures.
- [x] All formerly positional-only params become regular params.

### Pass 17: `SimplifyDynamicAttributes`

- [x] `getattr(obj, "foo")` → `obj.foo` for valid identifiers without `__` prefix.
- [x] `setattr(obj, "foo", val)` → `obj.foo = val` for valid identifiers without `__` prefix.
- [x] 3-arg `getattr(obj, "foo", default)` → skip.
- [x] `__`-prefixed attribute names → skip.
- [x] Attribute name not a valid identifier → skip.
- [x] `Clazz.__getattr__(obj, "foo")` → `obj.foo` only when `obj` statically typed as `Clazz` and no `__getattr__` override.

### Pass 18: `SimplifyFString`

- [x] `f"{x}"` → `str(x)`.
- [x] `f"{x}"` → `x` when `x` is statically `str`.
- [x] `f"{x}{y}"` → `x + y` only when both are statically `str`.
- [x] Simplification only applied when result is shorter or equal in bytes.

### Pass 19: `SimplifyEarlyExit`

- [x] `else` after `return` / `raise` / `continue` / `break` removed; body dedented.
- [x] `elif` after definite early exit becomes bare `if`.
- [x] Nested early-exit patterns resolved recursively.

### Pass 20: `SimplifyRaise`

- [x] `raise TypeError()` → `raise TypeError` for built-in exceptions.
- [x] Built-in exceptions with arguments left untouched.
- [x] Non-built-in exceptions left untouched.

### Pass 21: `SimplifyIfStmt`

- [x] Single-expression `if cond: func(x)` with no `else` → `cond and func(x)`.
- [x] Multi-statement `if` body not converted.
- [x] `if` with `else` not converted.

### Pass 22: `ConvertToTernary`

- [x] `if cond: return a\nelse: return b` → `return a if cond else b`.
- [x] `if cond: return a\nreturn b` (implicit else) → `return a if cond else b`.
- [x] Assignment form: all branches same target + same operator → ternary chain.
- [x] Mixed operators across branches → skip.

### Pass 23: `ConvertToLambda`

- [x] Single-expression `def f(args): return expr` → `f = lambda args: expr`.
- [x] Functions with docstrings not converted.
- [x] Decorators handled: `@dec\ndef f(): expr` → `f = dec(lambda: expr)`.
- [x] Functions with complex bodies (non-compressible to single expr) not converted.

### Pass 24: `HoistLiterals`

- [x] Short literal constants referenced once or twice → inlined when result is shorter in bytes.
- [x] Only literal types (int, float, str, bool, `None`, `...`) hoisted.
- [x] Definition removed after inlining.

### Pass 25: `RemovePass`

- [x] `pass` removed from all non-empty suites.
- [x] Sole `pass` in an otherwise-empty suite preserved.

### Pass 26: `RemoveTypingDecorators`

- [x] `@terser.hints.*` decorators removed.
- [x] `@typing.override` removed.
- [x] `@typing.final` removed.
- [x] Configured additional decorators removed.

### Pass 27: `InlineFunctions`

- [x] Single-expression or lambda-equivalent functions inlined at all call sites.
- [x] Module-private (`__`-prefixed) functions used exactly once inlined.
- [x] Module-internal-only functions used exactly once inlined.
- [x] `@terser.hints.inline`-marked functions inlined regardless of usage count.
- [x] Original definition removed after inlining.
- [x] Functions used in multiple call sites only inlined when criteria explicitly met.

### Pass 28: `InlineIntFlags`

- [x] Member references replaced with raw integer values at all use sites.
- [x] Class definition removed after inlining.
- [x] Only `enum.IntFlag`-only bases and no methods qualify.
- [x] `@terser.hints.inline` with other bases or methods → `raise` + stop.

### Pass 29: `CleanupImports`

- [x] Adjacent `import a; import b` → `import a, b`.
- [x] `from X import a; from X import b` → `from X import a, b`.
- [x] Unused module-level imports removed.
- [x] Names in `__all__` treated as used.
- [x] Function-local imports only removed if unused within that function scope.

### `__all__` Removal

- [x] `__all__` assignment removed from `module.body` after the final Transform pass cycle.
- [x] Removal is exact: `ast.Assign` with single `ast.Name` target `id == '__all__'`.
- [x] Augmented assignments (`__all__ += [...]`) are not matched and left in place.

### CLI

- [x] Every `TerserConfig` field has a corresponding CLI flag (see CLI Mapping table).
- [x] `--preserve-globals` comma-split and `mod:name` format parsed correctly.
- [x] `--preserve-locals` comma-split applied; no `mod:name` parsing.
- [x] `--optimize` sets both `remove_asserts=True` equivalent and `__debug__` → `False` folding.
- [x] `--threads` and `--transform-passes` accepted and passed to `TerserConfig`.
- [x] `--obfuscation-map FILE` writes populated `obfuscation_map` as JSON after all files processed.
- [x] `--define NAME` sets `defines[NAME]=True`; `--define NAME=0` sets `defines[NAME]=False`.