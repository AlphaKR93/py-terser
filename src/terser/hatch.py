import asyncio
from pathlib import Path
from typing import Any

import pathspec
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from terser.config import TransformConfig
from terser.terser import minify_project


class TerserBuildHook(BuildHookInterface):
    PLUGIN_NAME = "terser"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name == "sdist":
            return

        included_files = list(self.build_config.builder.recurse_included_files())
        py_files = [
            f for f in included_files
            if f.path.endswith(".py") or f.path.endswith(".pyw")
        ]
        if not py_files:
            return

        roots = set()
        for f in py_files:
            str_path = str(f.path)
            dist_path = str(f.distribution_path)
            if str_path.endswith(dist_path):
                root = str_path[:-len(dist_path)].rstrip("/\\")
                if root:
                    roots.add(root)

        if not roots:
            return

        config_opts = self.config.get("config", {})
        config = TransformConfig(
            passes=config_opts.get("passes", 5),
            apply_contracts=config_opts.get("apply_contracts", True),
            remove_literal_statements=config_opts.get("remove_literal_statements", False),
            combine_imports=config_opts.get("combine_imports", True),
            remove_annotations=config_opts.get("remove_annotations", True),
            remove_explicit_base=config_opts.get("remove_explicit_base", True),
            remove_explicit_return_none=config_opts.get("remove_explicit_return_none", True),
            fold_constants=config_opts.get("fold_constants", True),
            remove_debug=config_opts.get("remove_debug", True),
            remove_asserts=config_opts.get("remove_asserts", True),
            convert_pass=config_opts.get("convert_pass", True),
            remove_empty_exc_brackets=config_opts.get("remove_empty_exc_brackets", True),
            convert_posargs=config_opts.get("convert_posargs", True),
        )

        out_dir = Path(self.directory) / ".terser_build"
        out_dir.mkdir(parents=True, exist_ok=True)

        asyncio.run(
            minify_project(
                roots,
                config,
                out_dir,
                hoist_literals=self.config.get("hoist_literals", True),
                rename_locals=self.config.get("rename_locals", True),
                preserve_locals=self.config.get("preserve_locals"),
                rename_globals=self.config.get("rename_globals", False),
                preserve_globals=self.config.get("preserve_globals"),
            )
        )

        # Minified files are added via force_include; the originals must be excluded
        # from the normal package walk, or the wheel builder rejects the duplicate
        # distribution path.
        force_include = build_data.setdefault("force_include", {})
        exclude_patterns = []
        for f in py_files:
            minified_path = out_dir / f.distribution_path
            if minified_path.exists():
                force_include[str(minified_path)] = f.distribution_path
                exclude_patterns.append("/" + f.relative_path)

        if exclude_patterns:
            new_spec = pathspec.GitIgnoreSpec.from_lines(exclude_patterns)
            existing_spec = self.build_config.exclude_spec
            self.build_config.__dict__["exclude_spec"] = (
                pathspec.GitIgnoreSpec(list(existing_spec.patterns) + list(new_spec.patterns))
                if existing_spec is not None
                else new_spec
            )
