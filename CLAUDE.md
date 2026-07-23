# CLAUDE.md

`py-terser` (package `terser`) is a fork of [dflook/python-minifier](https://github.com/dflook/python-minifier), being rewritten to minify across a whole project. Planned to provide hatch build hook along with the CLI. The goal is to add a project-wide pipeline in addition to the original single-file pipeline. Source root is `src/`, package manager is `uv`.

Codebase is in mid-migration (dead imports, commented-out code, `# TEMP` markers, empty stubs) — ignore name errors that appear in the type checker. There is no test suite/framework wired up yet. `test.py` at the root is an ad-hoc manual script for IDE debugging, not a pytest target; do not run or modify it.

## Architecture

Pipelines live under `terser._pipeline`, consists of these components:

- `minify()` — new async minifier, shared across single-file and project-wide mode.
    1. Preprocess (`preprocessor.py`) — strips shebang, handles preprocessing (directives).
    2. Parse (`parser/parser.py`) — parses source into `ast.Module`, wrapping it in a `ModuleRef` (attached via the `ref()`/`NodeRef` mechanism, see below).
    3. Apply pre-transforms — apply transforms with `FLAGS <= 0`.
    4. Resolve names (`resolver/`) — two phase: `resolver.resolve()` in `resolver.py` walks the AST, binding every name to a `Binding` in its namespace (`ScopedNode`), mirroring CPython scoping rules. `binder/` (in `resolver/binder/__init__.py`, running `resolve_all` → `mark_exports` → `resolve_imports` → `bind`) then figures out `__all__`, module exports, and unresolved import targets (`UnresolvedModuleRef`) *within* a single module, deferring cross-module linking.
    5. Apply module transforms — apply transforms with `FLAGS <= 1`, repeat `config.passes` times. Stop iteration if `_is_node_modified` of all transforms is `False`.
    6. Module-level mangle — apply mangling for module-level names (locals/nonlocals, `__` prefixed names).
- Transformers — per-node rewrite passes, inherits `SuiteTransformer`. Some transformers need bindings already resolved (see `FLAGS`) — check the ordering there before adding a new one.
- Mangler — name-shortening (rename, hoist literals). Currently disconnected from the new minifier.

### Project-wide architecture

Project-wide pipeline stages live under `terser._pipeline`, run roughly in this order:

1. Resolve paths — `PathProvider` (`path_provider.py`) takes a set of file/dir paths, walks directories for `*.py`/`*.pyw`, and `align()`s them into a namespace tree of `ModuleSpec` (`terser.ast.ref.module.spec`). This must run and resolve (`await pp.resolve()`) before any module is parsed, since parsing needs a module's `ModuleSpec` to know its dotted path and how to resolve relative imports.
2. Process individual modules asynchronously (multi-threaded) via `minify`.
3. Linking (`linker.py`) — the actual project-aware step: once every module in the project has been through resolver, `link()` matches each module's `import_targets`/`wildcard_targets` against the full `project: dict[str, ModuleRef]` to resolve `import x.y` and`from x import *` across files. Wildcard imports can only be expanded once the target module's exports are known, which is why this is a separate, later pass.
4. Apply project transforms — apply transforms with `FLAGS <= 2`, repeat `config.passes` times.
5. Project-level mangle — apply project-wide mangling using linked information.
6. Apply mangle-sensitive transforms — apply transforms with `FLAGS <= 4`.

### Node references (`terser.ast.ref`)

AST nodes are plain `ast.AST` subclasses (re-exported from `terser/ast/ast.py`); metadata (parent, namespace, bindings, module spec, etc.) is never stored on the node itself. Instead, `NodeRef.new()` attaches a side-table object to each node via a hidden attribute, retrieved with `ref(node)`.

Which `NodeRef` subclass wraps a node is decided by `NodeRef._KLASSES[type(node)]`: plain nodes get a bare `NodeRef`, namespace-introducing nodes (`SCOPED_T` in `_scoped.py`) get a `ScopedNode` (adds `bindings`/`globals`/`nonlocals`), and `ast.Module` specifically gets `ModuleRef` (`ast/ref/_module/_module.py`, inherits `ScopedNode`), which additionally carries the module's `ModuleSpec`, `preserved`/`all`/`tainted` state, and the `import_targets`/`wildcard_targets` maps that `linker.py` consumes. When adding a new node kind that needs extra metadata, register it in `_KLASSES` rather than adding attributes to the AST node class.

### Name binding (`terser._pipeline.resolver.binder`)

After applying the pre-transform (phase 3 of `minify()`), the declaration of the name is bound. Bindings include `NameBinding`, `ImportBinding`, `UnresolvedBinding`, and `BuiltinBinding`. These will be used for project-wide processing.

## Stub files

There are some hand-written stubs (per the user's Python type-checking convention: complex types go in `.pyi` rather than runtime annotations to save resources) — check these when a type-checker error exists and the runtime source doesn't explain it.

## To-do

- Exclude `typing_extensions.py` automatically and convert references into `typing` if available
- Mangle module name
- Tree-shake
- Resolve `so`/`dll`/`dylib`/etc. and copy for project-wide minification

### Planned transforms (ordered, see `terser/_pipeline/transforms`)

- Contracts (`contracts.py`) `(Flags.REQUIRES_IMPORT_RESOLVE)`
    - Default contracts: `typing.cast(_, value) -> value` (leave only `value`), `typing.assert_never(x) -> None` (completely remove call), `typing.assert_type(x, _) -> x` (leave only `x`).
- Unfold `@lambda _: _()` constants (inline function body)
- Remove dummy assignments `(Flags.REQUIRES_IMPORT_RESOLVE)`
- Remove literal statements (`remove_literal_statements.py`) — SHOULD preserve docstrings, will process them right next.
- Remove docstrings `(param: also_modules)` — preserve docstrings in modules if `not also_modules`. preserve docstrings if decorated with `@terser_hints.preserve_docstring` (can be changed later).
- Combine imports `combine_imports.py`
- Cleanup local imports `(Flags.REQUIRES_IMPORT_RESOLVE)` — remove unused local imports, and global imports if `config.respect_all`.
- Remove annotations `remove_annotations.py`
- Remove `type` statements
- Remove typing classes `(Flags.REQUIRES_IMPORT_RESOLVE)`
    - bare `Protocol` (SHOULD ignore if decorated with `@typing.runtime_visible`)
    - `NamedTuple`, `NamedDict` (SHOULD convert constructors into `tuple`, `dict`)
- Remove `Generic`s `(Flags.REQUIRES_IMPORT_RESOLVE)`
- Remove `@overload`s `(Flags.REQUIRES_IMPORT_RESOLVE)`
    - Always `True` if `remove-typing-decorators` is selected
- Remove typing decorators `(Flags.REQUIRES_IMPORT_RESOLVE)`
    - `@typing.override`
    - `@typing.final`
- Remove explicit `return None` `remove_explicit_return_none.py`
- Remove explicit trailing `return`
- Fold constants `constant_folding.py`
    - constant operations
    - boolean operations (`x ==/is True` → `x`, `x ==/is False` → `not x`, …)
        - `__debug__`
        - `typing.TYPE_CHECKING` `(typing)`
        - `sys.version_info`, `sys.platform` `(module-sensitive)`
        - numbers (`0b1` → `1`, `1_000_000` → `1e6`, `0.0001` → `1e-4`)
    - strings (`\uXXXX` → raw represents, `f"{x}"` → `str(x)` or `x`, `f"{x}{y}"` → `x + y`)
    - collections ( `list()` → `[]`, `dict()` → `{}`, `tuple()` → `()`, `set([1])` → `{1,}` )
- Convert `typing_extensions` `(Flags.REQUIRES_IMPORT_RESOLVE)`
- Remove dead blocks
- Convert early exists
- Convert to inline
    - `if cond: func(x)` → `cond and func(x)`
    - `if fizz: foo(); else: bar()` → `foo() if fizz else bar()`
- Convert to lambda
    - `def foo(...): single_expr()` → `foo = lambda ...: single_expr()`
- Convert dynamic attribute access `(Flags.REQUIRES_IMPORT_RESOLVE)`
    - `getattr(obj, name)` → `obj.name`, `setattr(obj, name, value)` → `obj.name = value`
    - SHOULD ignore when:
        - `name` is not constant
        - `name` breaks Python naming requirements
        - `getattr` has default value
- Remove unnecessary base/meta classes `remove_object_base.py` `(Flags.REQUIRES_MODULE_RESOLVE)`
    - Default remove: `object`
- Remove empty exception brackets `remove_exception_brackets.py` `(Flags.REQUIRES_MODULE_RESOLVE)`
- `[EXPERIMENTAL]` Inline functions
- `[EXPERIMENTAL]` Inline `enum.IntFlag`s
- Convert pass `remove_pass.py`

### After mangling

- Convert positional arguments `remove_posargs.py` `(Flags.INFLUENCES_MANGLING)`
- Remove `__all__` `(Flags.INFLUENCES_MANGLING)`
