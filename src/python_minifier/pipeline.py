from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

import python_minifier._ast as ast
from python_minifier._ast.compare import CompareError, compare_ast
from python_minifier.config import TerserConfig
from python_minifier.preprocessor import Preprocessor, PreprocessResult
from python_minifier.parser import Parser, ParseResult
from python_minifier.linker import Linker
from python_minifier.transforms.runner import TransformRunner
from python_minifier.mangler import Mangler
from python_minifier.printer.module_printer import ModulePrinter

class UnstableMinification(RuntimeError):
    def __init__(self, exception, source, minified):
        self.exception = exception
        self.source = source
        self.minified = minified

    def __str__(self):
        return f'Unstable minification in {self.source}: {self.exception}'

@dataclass
class MinifiedResult:
    path: Path | None
    code: str
    original_size: int
    minified_size: int

class Pipeline:
    def __init__(self, config: TerserConfig):
        self.config = config

    def run(self, paths: list[str | Path]) -> list[MinifiedResult]:
        import os
        from dataclasses import replace

        # Resolve dotted name for a path relative to search roots
        def get_dotted_name(path, search_roots):
            for root in search_roots:
                abs_root = os.path.abspath(root)
                abs_path = os.path.abspath(path)
                if os.path.isdir(root) and abs_path.startswith(abs_root):
                    rel = os.path.relpath(abs_path, abs_root)
                    parts = rel.split(os.sep)
                    if parts[-1].endswith(('.py', '.pyw')):
                        parts[-1] = os.path.splitext(parts[-1])[0]
                    return '.'.join(parts)
                elif os.path.isfile(root) and abs_path == abs_root:
                    basename = os.path.basename(path)
                    if basename.endswith(('.py', '.pyw')):
                        basename = os.path.splitext(basename)[0]
                    return basename
            return None

        # 1. Preprocess & Parse in parallel using the same thread pool
        with ThreadPoolExecutor(max_workers=self.config.threads) as executor:
            futures = []
            for p in paths:
                path_obj = Path(p).resolve()
                futures.append((path_obj, executor.submit(self._run_stages_0_1, path_obj)))

            stages_0_1_results = []
            try:
                from tqdm import tqdm
                has_tqdm = True
            except ImportError:
                has_tqdm = False

            iterator = futures
            if has_tqdm and len(futures) > 1:
                iterator = tqdm(futures, desc="Minifying", unit="file")

            for path_obj, fut in iterator:
                try:
                    prep, parse_res = fut.result()
                    dotted_name = get_dotted_name(path_obj, paths)
                    stages_0_1_results.append({
                        "path": path_obj,
                        "prep": prep,
                        "parse_res": parse_res,
                        "module": parse_res.module,
                        "current_module_name": dotted_name,
                        "error": None
                    })
                except Exception as e:
                    stages_0_1_results.append({
                        "path": path_obj,
                        "prep": None,
                        "parse_res": None,
                        "module": None,
                        "current_module_name": None,
                        "error": e
                    })

        # 2. Link sequentially
        for item in stages_0_1_results:
            if item["error"]:
                continue
            try:
                file_config = replace(self.config, current_module_name=item["current_module_name"])
                linker = Linker(file_config)
                item["module"] = linker.link(item["module"], path=item["path"])
            except Exception as e:
                item["error"] = e

        # 3. Transform in parallel
        def run_transform(item):
            if item["error"]:
                return item
            try:
                file_config = replace(self.config, current_module_name=item["current_module_name"])
                runner = TransformRunner(file_config)
                item["module"] = runner.run(item["module"])
            except Exception as e:
                item["error"] = e
            return item

        with ThreadPoolExecutor(max_workers=self.config.threads) as executor:
            transformed_results = list(executor.map(run_transform, stages_0_1_results))

        # 4. Mangle sequentially
        for item in transformed_results:
            if item["error"]:
                continue
            try:
                file_config = replace(self.config, current_module_name=item["current_module_name"])
                mangler = Mangler(file_config)
                item["module"] = mangler.mangle(item["module"])
            except Exception as e:
                item["error"] = e

        # 5. Print in parallel
        def run_print(item):
            if item["error"]:
                return item
            try:
                item["minified_code"] = self._print_module(item["module"], item["prep"])
            except Exception as e:
                item["error"] = e
            return item

        with ThreadPoolExecutor(max_workers=self.config.threads) as executor:
            final_results = list(executor.map(run_print, transformed_results))

        # 6. Fallback/Error handling
        results = []
        for item in final_results:
            path_obj = item["path"]
            prep = item["prep"]
            error = item["error"]
            minified_code = item.get("minified_code")

            if error:
                if self.config.module_name_map and prep:
                    try:
                        fallback_prep = Preprocessor(self.config).preprocess(path=path_obj)
                        fallback_parse_res = Parser(self.config).parse(fallback_prep.source, str(path_obj))
                        module = fallback_parse_res.module

                        file_config = replace(self.config, current_module_name=item["current_module_name"])
                        linker = Linker(file_config)
                        module = linker.link(module, path=path_obj)

                        fallback_config = replace(file_config, hoist_literals=False)
                        runner = TransformRunner(fallback_config)
                        module = runner.run(module)
                        mangler = Mangler(fallback_config)
                        module = mangler.mangle(module)

                        minified_code = self._print_module(module, fallback_prep)
                        error = None
                    except Exception as fallback_err:
                        error = fallback_err

                if error:
                    if self.config.module_name_map:
                        raise RuntimeError(f"Error minifying {path_obj}: {error}") from error
                    else:
                        minified_code = prep.source if prep else ""

            results.append(MinifiedResult(
                path=path_obj,
                code=minified_code,
                original_size=len(prep.source) if prep else 0,
                minified_size=len(minified_code) if minified_code else 0
            ))

        return results

    def run_source(self, source: str, filename: str) -> MinifiedResult:
        try:
            # Stage 0: Preprocess
            prep = Preprocessor(self.config).preprocess(source=source)

            # Stage 1: Parse
            parse_res = Parser(self.config).parse(prep.source, filename)
            module = parse_res.module

            # Stage 2: Link
            linker = Linker(self.config)
            module = linker.link(module, path=prep.path)

            # Stage 3: Transform
            runner = TransformRunner(self.config)
            module = runner.run(module)

            # Stage 4: Mangle
            mangler = Mangler(self.config)
            module = mangler.mangle(module)

            # Stage 5: Print
            minified_code = self._print_module(module, prep)
        except Exception as e:
            if self.config.module_name_map:
                try:
                    prep = Preprocessor(self.config).preprocess(source=source)
                    parse_res = Parser(self.config).parse(prep.source, filename)
                    module = parse_res.module

                    linker = Linker(self.config)
                    module = linker.link(module, path=prep.path)

                    from dataclasses import replace
                    fallback_config = replace(self.config, hoist_literals=False)
                    runner = TransformRunner(fallback_config)
                    module = runner.run(module)
                    mangler = Mangler(fallback_config)
                    module = mangler.mangle(module)

                    minified_code = self._print_module(module, prep)
                except Exception:
                    raise e
            else:
                return MinifiedResult(
                    path=None,
                    code=source,
                    original_size=len(source),
                    minified_size=len(source)
                )

        return MinifiedResult(
            path=prep.path,
            code=minified_code,
            original_size=len(source),
            minified_size=len(source if minified_code is None else minified_code)
        )

    def _run_stages_0_1(self, path: Path) -> tuple[PreprocessResult, ParseResult]:
        prep = Preprocessor(self.config).preprocess(path=path)
        parse_res = Parser(self.config).parse(prep.source, str(path))
        return prep, parse_res

    def _print_module(self, module: ast.Module, prep: PreprocessResult) -> str:
        # Sort out __future__ imports to ensure they are at the top
        if isinstance(module, ast.Module):
            future_stmts = []
            other_stmts = []
            docstring_stmt = None
            body = module.body
            if body:
                first = body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, (ast.Constant, ast.Str)):
                    val = getattr(first.value, 'value', getattr(first.value, 's', None))
                    if isinstance(val, str):
                        docstring_stmt = first
                        body = body[1:]
                for stmt in body:
                    if isinstance(stmt, ast.ImportFrom) and stmt.module == '__future__':
                        future_stmts.append(stmt)
                    else:
                        other_stmts.append(stmt)
                new_body = []
                if docstring_stmt is not None:
                    new_body.append(docstring_stmt)
                new_body.extend(future_stmts)
                new_body.extend(other_stmts)
                module.body = new_body

        # Print AST to source (no transformations)
        printer = ModulePrinter(prefer_single_line=self.config.prefer_single_line)
        printer(module)
        minified = printer.code

        # AST stability check
        try:
            reparsed = ast.parse(minified, 'python_minifier.unparse output')
        except SyntaxError as e:
            raise UnstableMinification(e, str(prep.path) if prep else '', minified) from e

        try:
            compare_ast(module, reparsed)
        except CompareError as e:
            raise UnstableMinification(e, str(prep.path) if prep else '', minified) from e

        # Prepend shebang if needed
        if self.config.preserve_shebang and prep.shebang:
            return prep.shebang + '\n' + minified

        return minified
