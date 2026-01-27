import os
import sys
import python_minifier.ast as ast

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from python_minifier.rename import add_namespace, bind_names, resolve_names, rename_literals
from python_minifier.rename.renamer import NameAssigner, add_assigned, name_filter, all_bindings
from python_minifier.printer import ModulePrinter
from python_minifier.transforms.remove_environment_checks import RemoveEnvironmentChecks
from python_minifier.transforms.combine_imports import CombineImports
from python_minifier.transforms.remove_annotations import RemoveAnnotations
from python_minifier.transforms.remove_annotations_options import RemoveAnnotationsOptions
from python_minifier.transforms.remove_pass import RemovePass
from python_minifier.transforms.remove_literal_statements import RemoveLiteralStatements
from python_minifier.transforms.remove_posargs import remove_posargs
from python_minifier.transforms.remove_object_base import RemoveObject
from python_minifier.transforms.remove_asserts import RemoveAsserts
from python_minifier.transforms.remove_debug import RemoveDebug
from python_minifier.transforms.remove_explicit_return_none import RemoveExplicitReturnNone
from python_minifier.transforms.remove_inline_functions import RemoveInlineFunctions
from python_minifier.transforms.remove_typing_variables import RemoveTypingVariables
from python_minifier.transforms.constant_folding import FoldConstants
from python_minifier.transforms.remove_exception_brackets import remove_no_arg_exception_call
from python_minifier.transforms.remove_unused_imports import remove_unused_imports


@dataclass(frozen=True)
class PackageMinifyOptions:
    package_path: str
    remove_annotations: RemoveAnnotationsOptions = RemoveAnnotationsOptions()
    remove_pass: bool = True
    remove_literal_statements: bool = True
    combine_imports: bool = True
    hoist_literals: bool = True
    mangle: bool = False
    preserved_names: frozenset[str] = frozenset({})
    remove_unused_imports: bool = True
    preserved_imports: frozenset[str] = frozenset({})
    remove_object_base: bool = True
    convert_posargs_to_args: bool = True
    preserve_shebang: bool = False
    remove_asserts: bool = False
    remove_debug: bool = False
    remove_environment_checks: bool = True
    remove_explicit_return_none: bool = True
    remove_builtin_exception_brackets: bool = True
    constant_folding: bool = True
    allow_utf8_names: bool = True
    remove_inline_functions: bool = True
    remove_typing_variables: bool = True
    obfuscate_module_names: bool = False


class AbstractModule(NamedTuple):
    package: str
    module: ast.Module


_EMPTY = AbstractModule("", None)  # pyright: ignore[reportArgumentType]


class ProjectMinifier:
    root_path: str
    packages: dict[PackageMinifyOptions, dict[str, ast.Module]]  # path -> PackageMinifyOptions
    modules: dict[str, AbstractModule] = {}  # dotted.name -> ast.Module
    path_mapping: dict[str, str] = {}  # old_path -> new_path

    def __init__(
        self,
        root_path: str,
        /,
        *packages: PackageMinifyOptions,
        python_version: "sys._version_info" = sys.version_info,
        verbose: bool = False,
    ):
        self.python_version = python_version
        self.verbose = verbose
        self.root_path = root_path
        self.packages = {
            PackageMinifyOptions(**(package.__dict__ | {"package_path": os.path.abspath(os.path.join(root_path, package.package_path))})): {}
            for package in packages
        }

    def _load_module(self, package: PackageMinifyOptions, root: str, file: str):
        full_path = os.path.join(root, file)
        rel_path = os.path.relpath(full_path, self.root_path)

        module_name = rel_path.replace(os.path.sep, ".")[:-3]
        is_package = False

        if file == "__init__.py":
            module_name = os.path.dirname(rel_path).replace(os.path.sep, ".")
            if module_name == ".":
                module_name = ""
            is_package = True

        if module_name == ".":
            return

        with open(full_path, "r", encoding="utf-8") as f:
            source = f.read().replace("#if !__debug__:", "")

        try:
            tree = ast.parse(source, full_path)
        except SyntaxError as e:
            print(f"Error parsing {full_path}: {e}")
            return

        ast.add_parent(tree)
        add_namespace(tree)

        if package.combine_imports:
            tree = CombineImports()(tree)

        bind_names(tree)
        resolve_names(tree)

        self.packages[package][full_path] = tree

        if module_name:
            self.modules[module_name] = AbstractModule(
                module_name if is_package else ".".join(module_name.split(".")[:-1]), tree
            )

        if self.verbose:
            print("Loaded module", full_path)

    def load_project(self):
        for package in self.packages.keys():
            for root, _, files in os.walk(package.package_path):
                for file in files:
                    if file.endswith(".py"):
                        self._load_module(package, root, file)

    def resolve_relative_import(self, current_module_name, level, module_part):
        current_pkg = self.modules.get(current_module_name, _EMPTY).package
        pkg_parts = current_pkg.split(".") if current_pkg else []

        if level > 0:
            pop_count = level - 1
            if pop_count > len(pkg_parts):
                return None

            if pop_count > 0:
                target_pkg_parts = pkg_parts[:-pop_count]
            else:
                target_pkg_parts = pkg_parts

            target_pkg = ".".join(target_pkg_parts)

            if module_part:
                return f"{target_pkg}.{module_part}" if target_pkg else module_part
            else:
                return target_pkg
        return None

    def _get_module_preserved_names(
        self, preserved_options: frozenset[str], current_module_name: str | None
    ) -> set[str]:
        """
        Parse preserved options and return the set of names to preserve for the current module.
        Supports 'name' (global) and 'module.path:name' (scoped) formats.
        """
        preserved_names = set()

        for p in preserved_options:
            if ":" in p:
                # Scoped preservation: module.name:variable
                mod_part, name_part = p.split(":", 1)
                if current_module_name == mod_part:
                    preserved_names.add(name_part)
            else:
                # Global preservation
                preserved_names.add(p)

        return preserved_names

    def resolve_cross_module_references(self):
        print("Resolving cross-module references...")

        path_to_name = {v.module: k for k, v in self.modules.items()}

        for project, modules in self.packages.items():
            for path, module in modules.items():
                current_module_name = path_to_name.get(module)
                # [Modified] Apply preserved names based on module scope
                preserved_for_module = self._get_module_preserved_names(project.preserved_names, current_module_name)

                for binding in module.bindings:
                    if binding.name in preserved_for_module:
                        # Mark for export instead of disallowing rename
                        binding.export_as = binding.name

        for project, modules in self.packages.items():
            for path, module in modules.items():
                current_module_name = path_to_name.get(module)

                # Store tuples of (namespace, binding) to remove
                bindings_to_remove = []

                # [Modified] Use all_bindings to traverse nested scopes (functions, classes)
                # This ensures imports inside functions are also resolved and minified.
                for namespace, binding in all_bindings(module):
                    # ... (existing logic for cross-reference resolution)
                    import_node = None
                    alias_node = None

                    for ref in binding.references:
                        if isinstance(ref, ast.alias):
                            alias_node = ref
                            parent = ref
                            while hasattr(parent, "_parent"):
                                parent = parent._parent
                                if isinstance(parent, ast.ImportFrom):
                                    import_node = parent
                                    break
                            if import_node:
                                break

                    if import_node:
                        target_module_name = None
                        if import_node.level > 0:
                            target_module_name = self.resolve_relative_import(
                                current_module_name, import_node.level, import_node.module
                            )
                        else:
                            target_module_name = import_node.module

                        if target_module_name:
                            target_module = self.modules.get(target_module_name)

                            if target_module:
                                imported_name = alias_node.name
                                target_binding = None

                                for b in target_module.module.bindings:
                                    if b.name == imported_name:
                                        target_binding = b
                                        break

                                if target_binding:
                                    if target_binding is binding:
                                        continue

                                    if self.verbose:
                                        print(
                                            f"Linked {path}: {binding.name} -> {target_module_name}.{target_binding.name}"
                                        )

                                    # [Modified] Check preservation using scoped logic for the target module?
                                    # The target binding's disallow_rename is already handled in the first loop above based on its own module name.
                                    # Here we just propagate the disallow_rename if the local alias is preserved/disallowed.

                                    # Note: project.preserved check here strictly needs to check if THIS binding (in current module) is preserved.
                                    current_module_preserved = self._get_module_preserved_names(
                                        project.preserved_names, current_module_name
                                    )

                                    if not binding.allow_rename or binding.name in current_module_preserved:
                                        target_binding.disallow_rename()

                                    alias_node._is_project_reference = True

                                    for ref_node in list(binding.references):
                                        target_binding.add_reference(ref_node)

                                    bindings_to_remove.append((namespace, binding))

                for namespace, b in bindings_to_remove:
                    if b in namespace.bindings:
                        namespace.bindings.remove(b)

    def _get_module_name_from_path(self, path):
        rel_path = os.path.relpath(path, self.root_path)
        if path.endswith("__init__.py"):
            module_name = os.path.dirname(rel_path).replace(os.path.sep, ".")
            if module_name == ".":
                return ""
            return module_name
        else:
            return rel_path.replace(os.path.sep, ".")[:-3]

    def obfuscate_modules(self):
        print("Obfuscating module names...")
        module_mapping = {}  # old_dotted_name -> new_dotted_name
        self.path_mapping = {}  # old_full_path -> new_full_path

        # 1. Identify preserved module paths
        preserved_module_paths = set()

        # Also track which modules are in obfuscated packages
        obfuscated_modules = set()

        for package, modules_dict in self.packages.items():
            for p in package.preserved_names:
                if ":" in p:
                    preserved_module_paths.add(p.split(":")[0])
                else:
                    # Check if p matches a loaded module name
                    if p in self.modules:
                        preserved_module_paths.add(p)

            if package.obfuscate_module_names:
                for path in modules_dict.keys():
                    mod_name = self._get_module_name_from_path(path)
                    if mod_name:
                        obfuscated_modules.add(mod_name)

        class Node:
            def __init__(self, name=""):
                self.name = name
                self.new_name = None
                self.children = {}
                self.locked = False
                self.is_module = False  # Does this node correspond to an actual module?

        root = Node()

        # 2. Build global tree from all modules
        all_modules = set()
        for pkg_modules in self.packages.values():
            for path in pkg_modules.keys():
                mod_name = self._get_module_name_from_path(path)
                if mod_name:
                    all_modules.add(mod_name)

        # Ensure we also add preserved paths even if not loaded (unlikely but for consistency)
        for p in preserved_module_paths:
            all_modules.add(p)

        for mod_name in sorted(all_modules):
            parts = mod_name.split(".")
            curr = root
            for part in parts:
                if part not in curr.children:
                    curr.children[part] = Node(part)
                curr = curr.children[part]
            curr.is_module = True

        # 3. Mark locked nodes
        # A node is locked if:
        # - It is in preserved_module_paths (or part of the path)
        # - It represents a module that is NOT in obfuscated_modules (if it is a module)
        # - Note: Directories that are not modules themselves but contain preserved modules
        #   must be locked? Yes.

        # Pass 1: Explicit preservation
        for p in preserved_module_paths:
            parts = p.split(".")
            curr = root
            for part in parts:
                if part in curr.children:
                    curr = curr.children[part]
                    curr.locked = True

        # Pass 2: Lock non-obfuscated modules and their parents?
        # Actually, if a module is not in 'obfuscated_modules', it should be locked.
        # But 'obfuscated_modules' only contains names from packages where obfuscation is ON.
        # So if a module is not in that set, we must preserve it.

        for mod_name in all_modules:
            if mod_name not in obfuscated_modules:
                # Lock the whole path
                parts = mod_name.split(".")
                curr = root
                for part in parts:
                    curr = curr.children[part]
                    curr.locked = True

        # 4. Assign names
        def assign_names(node, prefix_parts):
            # Collect children to rename vs preserved
            to_rename = []
            used_names = set()

            for name, child in node.children.items():
                if child.locked:
                    child.new_name = name
                    used_names.add(name)
                else:
                    to_rename.append(child)

            # Determine unicode allowance.
            # We default to True if ANY package allows it? Or check specific package?
            # Since we built a global tree, it's hard to map back to specific package options for directories.
            # We'll assume True if any package allows it, or just default True as per user instructions (Milestone 2-7).
            # "난독화 이름에 유니코드 허용" is checked.
            scope_gen = name_filter(allow_unicode=True)

            # Sort for determinism
            to_rename.sort(key=lambda n: n.name)

            for child in to_rename:
                while True:
                    candidate = next(scope_gen)
                    if candidate not in used_names:
                        child.new_name = candidate
                        used_names.add(candidate)
                        break

            for child in node.children.values():
                assign_names(child, prefix_parts + [child.new_name])

        assign_names(root, [])

        # 5. Populate mappings
        def populate_map(node, old_dotted, new_dotted):
            if old_dotted:
                module_mapping[old_dotted] = new_dotted

            for name, child in node.children.items():
                old_sub = f"{old_dotted}.{name}" if old_dotted else name
                new_sub = f"{new_dotted}.{child.new_name}" if new_dotted else child.new_name
                populate_map(child, old_sub, new_sub)

        populate_map(root, "", "")

        # Update path_mapping
        for path in [p for sublist in self.packages.values() for p in sublist.keys()]:
            old_mod = self._get_module_name_from_path(path)
            if old_mod in module_mapping:
                new_mod = module_mapping[old_mod]
                new_rel_path = new_mod.replace(".", os.path.sep)
                if path.endswith("__init__.py"):
                    new_rel_path = os.path.join(new_rel_path, "__init__.py")
                else:
                    new_rel_path = new_rel_path + ".py"

                self.path_mapping[path] = os.path.join(self.root_path, new_rel_path)

        # 6. Rewrite Imports
        for modules in self.packages.values():
            for path, module in modules.items():
                current_mod_name = self._get_module_name_from_path(path)

                # Determine current package's new name (for relative import resolution)
                current_pkg = self.modules.get(current_mod_name, _EMPTY).package
                new_current_pkg = module_mapping.get(current_pkg, current_pkg)

                for node in ast.walk(module):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in module_mapping:
                                old_name = alias.name
                                new_name = module_mapping[old_name]

                                if alias.asname is None:
                                    # If renamed, usage of `old_name` becomes `new_name`.
                                    # Use _update_attribute_usages to handle the attribute chain.
                                    self._update_attribute_usages(module, old_name, new_name)

                                alias.name = new_name

                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            # Resolve absolute
                            target_mod = None
                            if node.level > 0:
                                target_mod = self.resolve_relative_import(current_mod_name, node.level, node.module)
                            else:
                                target_mod = node.module

                            if target_mod and target_mod in module_mapping:
                                new_target = module_mapping[target_mod]

                                if node.level == 0:
                                    node.module = new_target
                                else:
                                    # Reconstruct relative path
                                    # new_target is full path "a.b"
                                    # new_current_pkg is full path "a" (if current was lib)

                                    current_pkg_parts = new_current_pkg.split(".") if new_current_pkg else []
                                    if node.level - 1 <= len(current_pkg_parts):
                                        # valid relative import
                                        base_parts = current_pkg_parts[: len(current_pkg_parts) - (node.level - 1)]
                                        base_pkg = ".".join(base_parts)

                                        if new_target == base_pkg:
                                            node.module = None
                                        elif new_target.startswith(base_pkg + "."):
                                            node.module = new_target[len(base_pkg) + 1 :]
                                        else:
                                            # Fallback/no-change if structural divergence detected
                                            pass

    def _update_attribute_usages(self, module, old_name, new_name):
        """
        Updates usages like `lib.foo` to `lib.a` when `import lib.foo` was renamed to `import lib.a`.
        """
        parts = old_name.split(".")
        root_name = parts[0]

        binding = None
        for b in module.bindings:
            if b.name == root_name:
                binding = b
                break

        if not binding:
            return

        new_parts = new_name.split(".")
        if len(parts) != len(new_parts):
            return

        # Rename the root binding if needed
        if parts[0] != new_parts[0]:
            if binding.allow_rename:
                binding.rename(new_parts[0])

        # Traverse references for attributes
        for ref in binding.references:
            if isinstance(ref, ast.Name) and isinstance(ref.ctx, ast.Load):
                curr = ref
                # Verify chain
                p = ast.get_parent(curr)

                nodes_to_update = []
                cursor = p
                valid_chain = True

                # We look for attribute chain matching parts[1:]
                # e.g. old: lib.foo.bar -> new: a.b.c
                # ref is 'lib' (renamed to 'a'). Parent is Attribute(attr='foo').

                for i in range(1, len(parts)):
                    if isinstance(cursor, ast.Attribute) and cursor.attr == parts[i]:
                        nodes_to_update.append((cursor, new_parts[i]))
                        cursor = ast.get_parent(cursor)
                    else:
                        valid_chain = False
                        break

                if valid_chain:
                    for node, new_attr in nodes_to_update:
                        node.attr = new_attr

    def minify(self):
        self.load_project()
        self.resolve_cross_module_references()

        for package, modules in self.packages.items():
            if package.remove_literal_statements:
                for path, module in modules.items():
                    modules[path] = RemoveLiteralStatements()(module)

        for package, modules in self.packages.items():
            if package.remove_annotations:
                for path, module in modules.items():
                    modules[path] = RemoveAnnotations(package.remove_annotations)(module)

        for package, modules in self.packages.items():
            if package.remove_object_base:
                for path, module in modules.items():
                    modules[path] = RemoveObject()(module)

        for package, modules in self.packages.items():
            if package.remove_explicit_return_none:
                for path, module in modules.items():
                    modules[path] = RemoveExplicitReturnNone()(module)

        for package, modules in self.packages.items():
            if package.constant_folding:
                for path, module in modules.items():
                    modules[path] = FoldConstants()(module)

        for package, modules in self.packages.items():
            if package.remove_debug:
                for path, module in modules.items():
                    modules[path] = RemoveDebug()(module)

        for package, modules in self.packages.items():
            if package.remove_asserts:
                for path, module in modules.items():
                    modules[path] = RemoveAsserts()(module)

        for package, modules in self.packages.items():
            if package.remove_environment_checks:
                for path, module in modules.items():
                    modules[path] = RemoveEnvironmentChecks(self.python_version)(module)

        for package, modules in self.packages.items():
            if package.remove_builtin_exception_brackets:
                for path, module in modules.items():
                    if not module.tainted:
                        remove_no_arg_exception_call(module)

        # Module obfuscation (renaming)
        self.obfuscate_modules()

        for package, modules in self.packages.items():
            if package.remove_unused_imports:
                for path, module in modules.items():
                    if not path.endswith("__init__.py"):
                        module = remove_unused_imports(module, package.preserved_imports)

        for package, modules in self.packages.items():
            if package.remove_inline_functions:
                for path, module in modules.items():
                    modules[path] = RemoveInlineFunctions()(module)

        for package, modules in self.packages.items():
            if package.remove_typing_variables:
                for path, module in modules.items():
                    modules[path] = RemoveTypingVariables()(module)

        for package, modules in self.packages.items():
            if package.hoist_literals:
                for path, module in modules.items():
                    rename_literals(module)

        for package, modules in self.packages.items():
            for path, module in modules.items():
                add_assigned(module)

        # Prepare map for name resolution (module object -> dotted name)
        # We need this because 'modules' dict here is path->module, but we track names by dotted name in self.modules
        path_to_name = {v.module: k for k, v in self.modules.items()}

        for package, modules in self.packages.items():
            assigner = NameAssigner(name_generator=name_filter(allow_unicode=package.allow_utf8_names))
            if package.mangle:
                for path, module in modules.items():
                    # [Modified] Calculate preserved names for this specific module
                    current_module_name = path_to_name.get(module)
                    module_specific_preserved = self._get_module_preserved_names(
                        package.preserved_names, current_module_name
                    )

                    assigner(module, prefix_globals=False, reserved_globals=module_specific_preserved)

        for package, modules in self.packages.items():
            for path, module in modules.items():
                if package.convert_posargs_to_args:
                    module = remove_posargs(module)

                if package.remove_pass:
                    modules[path] = RemovePass()(module)

                modules[path] = module

        for package, modules in self.packages.items():
            for path, module in modules.items():
                # Determine output path using mapping or fallback to original
                output_path = self.path_mapping.get(path, path)

                # Create directories for new path
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                minified_code = ModulePrinter()(module)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(minified_code)
                if path != os.path.abspath(output_path):
                    Path(path).unlink()
                if self.verbose:
                    print(f"Minified: {path} -> {output_path}")

    __call__ = minify
