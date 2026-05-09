"""Cross-module call graph construction.

Builds a mapping of qualified caller name -> set of qualified callee names
from a list of ParsedFiles. Used by Project.call_graph and any detector
that needs to walk caller/callee relationships across files.

Resolution is heuristic: we only emit edges we can resolve confidently. A
caller may have undetected callees (recall < 1) — that's intentional.
Targets we can resolve:

    self.foo()                         -> enclosing class's `foo` method
    obj.foo() with `obj: ClassName`    -> ClassName.foo method
    obj.foo() with `obj = ClassName()` -> ClassName.foo method
    module.foo() (module is imported)  -> module.foo (resolved via module_paths)
    foo() (foo is a top-level def)     -> this_module.foo

Anything else (chained calls, dict lookups, decorated calls, callbacks
passed as args, dynamic dispatch) is skipped silently.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from posd_lint.parse import ParsedFile


@dataclass
class CallSite:
    """One call: which function makes it, where it lands, and the args.

    Used by detectors that need per-call detail (param-forwarding analysis)
    rather than just the aggregated caller -> callees edges. callee_qualname
    is None for unresolved external calls when iterated raw; build_call_sites
    filters those out.
    """
    caller_qualname: str
    callee_qualname: Optional[str]
    call: ast.Call
    file_path: str
    func_node: ast.AST  # the FunctionDef containing the call


def build_call_graph(
    files: list[ParsedFile],
    qualname_for: callable,
    module_paths: dict[str, str],
    classes_by_name: dict,
    local_var_classes_for: callable,
) -> dict[str, set[str]]:
    """Produce {caller_qualname: {callee_qualname, ...}} across all files."""
    edges: dict[str, set[str]] = defaultdict(set)
    for site in _iter_call_sites(files, qualname_for, module_paths, classes_by_name, local_var_classes_for):
        if site.callee_qualname is None:
            continue
        edges[site.caller_qualname].add(site.callee_qualname)
    return dict(edges)


def build_call_sites(
    files: list[ParsedFile],
    qualname_for: callable,
    module_paths: dict[str, str],
    classes_by_name: dict,
    local_var_classes_for: callable,
) -> list[CallSite]:
    """Per-call-site detail: caller, callee, the Call node, and its enclosing function.

    The plain call_graph collapses many calls into one set entry; detectors
    that need to know "which arguments did caller pass to callee at *this*
    call site" need the un-collapsed form. Only resolved sites are returned.
    """
    return [
        s for s in _iter_call_sites(files, qualname_for, module_paths, classes_by_name, local_var_classes_for)
        if s.callee_qualname is not None
    ]


def build_external_calls(
    files: list[ParsedFile],
    qualname_for: callable,
    module_paths: dict[str, str],
    classes_by_name: dict,
    local_var_classes_for: callable,
) -> dict[str, set[str]]:
    """Map caller_qualname -> set of *external* dotted symbols it calls.

    "External" means the call target couldn't be resolved to a project-internal
    function. Best-effort dotted form: `requests.get`, `pathlib.Path.read_text`,
    `print` (no module prefix when bare). Used by the effects layer to look up
    side-effects in a curated registry — calls into stdlib / third-party.
    """
    out: dict[str, set[str]] = defaultdict(set)
    file_indexes = {f.path: _FileIndex.build(f, qualname_for(f.path)) for f in files}
    for f in files:
        idx = file_indexes[f.path]
        local_classes = local_var_classes_for(f)
        for caller_qual, func_node, enclosing_class in idx.functions:
            for call in _direct_calls_in(func_node):
                for ext in _external_dotted_names(call, idx, local_classes, classes_by_name, module_paths):
                    out[caller_qual].add(ext)
    return dict(out)


def _iter_call_sites(
    files: list[ParsedFile],
    qualname_for: callable,
    module_paths: dict[str, str],
    classes_by_name: dict,
    local_var_classes_for: callable,
):
    file_indexes = {f.path: _FileIndex.build(f, qualname_for(f.path)) for f in files}
    for f in files:
        idx = file_indexes[f.path]
        local_classes = local_var_classes_for(f)
        resolver = _CallResolver(
            file_index=idx,
            module_paths=module_paths,
            classes_by_name=classes_by_name,
            local_classes=local_classes,
            file_indexes=file_indexes,
        )
        for caller_qual, func_node, enclosing_class in idx.functions:
            for call in _direct_calls_in(func_node):
                callee = resolver.resolve(call, enclosing_class)
                yield CallSite(
                    caller_qualname=caller_qual,
                    callee_qualname=callee,
                    call=call,
                    file_path=f.path,
                    func_node=func_node,
                )


def _external_dotted_names(
    call: ast.Call,
    idx: "_FileIndex",
    local_classes: dict[str, str],
    classes_by_name: dict,
    module_paths: dict[str, str],
):
    """Yield candidate dotted names a call may target, when it's external.

    We emit multiple candidates per site so the effect-db lookup can match
    permissively: `obj.read_text()` where `obj` is a `Path` yields
    `pathlib.Path.read_text`, `Path.read_text`, and `read_text`. The matcher
    keeps whichever it finds first.
    """
    func = call.func
    if isinstance(func, ast.Name):
        name = func.id
        # Resolved-internal name calls won't reach here (build_external_calls
        # is independent of the resolver), so we still emit them as candidates;
        # the matcher only flags symbols listed in the registry — internal
        # names won't collide with stdlib entries unless someone names a func
        # `open` in a project file (which we accept as a known false-positive).
        if name in idx.from_imports:
            source_module, original = idx.from_imports[name]
            target_module = f"{source_module}.{original}" if source_module else original
            if target_module in module_paths:
                return  # internal — don't emit external candidate
            yield f"{source_module}.{original}" if source_module else original
            yield original
            return
        if name in idx.top_level_names:
            return  # local def — handled by the call graph
        yield f"builtins.{name}"
        yield name
        return

    if isinstance(func, ast.Attribute):
        method = func.attr
        receiver = func.value
        if isinstance(receiver, ast.Name):
            rname = receiver.id
            if rname == "self":
                return  # internal
            if rname in idx.import_aliases:
                module = idx.import_aliases[rname]
                if module in module_paths:
                    return  # resolved internally already
                yield f"{module}.{method}"
                yield f"{rname}.{method}"
                return
            if rname in idx.from_imports:
                source_module, original = idx.from_imports[rname]
                target_module = f"{source_module}.{original}" if source_module else original
                if target_module in module_paths:
                    return
                if source_module:
                    yield f"{source_module}.{original}.{method}"
                yield f"{original}.{method}"
                yield f"{method}"
                return
            klass = local_classes.get(rname)
            if klass is not None:
                # Project-internal class — handled by call graph if method exists.
                yield f"{klass}.{method}"
                yield method
                return
            yield f"{rname}.{method}"
            yield method
            return
        if isinstance(receiver, ast.Attribute):
            # Walk the attribute chain to its rightmost Name (or give up).
            chain: list[str] = [method]
            cur: ast.expr = receiver
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            chain.reverse()
            if isinstance(cur, ast.Name):
                root_name = cur.id
                # `self.foo.bar.baz()` — emit the tail-method names so the
                # registry can match e.g. `messages.create` on `self.client.messages.create`.
                if root_name == "self":
                    if len(chain) >= 2:
                        yield ".".join(chain[-2:])
                    yield method
                    return
                if root_name in idx.import_aliases:
                    module = idx.import_aliases[root_name]
                    yield ".".join([module] + chain)
                    yield ".".join([root_name] + chain)
                    if len(chain) >= 2:
                        yield ".".join(chain[-2:])
                    yield method
                    return
                yield ".".join([root_name] + chain)
                if len(chain) >= 2:
                    yield ".".join(chain[-2:])
                yield method
                return
        yield method


class _FileIndex:
    """Per-file information needed for call resolution.

    - module_qualname: dotted name of this module.
    - functions: every function/method with its caller-qualname and
      enclosing class (None for free functions).
    - top_level_names: names defined at module scope (functions or classes)
      so a bare `foo()` inside this file can resolve to `module.foo`.
    - import_aliases: local-name -> dotted-module-path for `import X` and
      `import X as Y` forms. Used when we see `mod.foo()`.
    - from_imports: local-name -> (source_module, original_name) for
      `from X import Y [as Z]`. Used when we see a bare `Y()` whose target
      lives in another file.
    """

    def __init__(
        self,
        module_qualname: str,
        functions: list[tuple[str, ast.AST, Optional[ast.ClassDef]]],
        top_level_names: set[str],
        import_aliases: dict[str, str],
        from_imports: dict[str, tuple[str, str]],
    ) -> None:
        self.module_qualname = module_qualname
        self.functions = functions
        self.top_level_names = top_level_names
        self.import_aliases = import_aliases
        self.from_imports = from_imports

    @classmethod
    def build(cls, f: ParsedFile, module_qualname: str) -> "_FileIndex":
        functions: list[tuple[str, ast.AST, Optional[ast.ClassDef]]] = []
        top_level_names: set[str] = set()
        import_aliases: dict[str, str] = {}
        from_imports: dict[str, tuple[str, str]] = {}

        for stmt in f.tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                top_level_names.add(stmt.name)
                qual = f"{module_qualname}.{stmt.name}" if module_qualname else stmt.name
                functions.append((qual, stmt, None))
            elif isinstance(stmt, ast.ClassDef):
                top_level_names.add(stmt.name)
                for item in stmt.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qual_parts = [p for p in (module_qualname, stmt.name, item.name) if p]
                        functions.append((".".join(qual_parts), item, stmt))
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    local = alias.asname or alias.name.split(".")[0]
                    import_aliases[local] = alias.name
            elif isinstance(stmt, ast.ImportFrom):
                module = stmt.module or ""
                for alias in stmt.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    from_imports[local] = (module, alias.name)

        return cls(module_qualname, functions, top_level_names, import_aliases, from_imports)


class _CallResolver:
    def __init__(
        self,
        file_index: _FileIndex,
        module_paths: dict[str, str],
        classes_by_name: dict,
        local_classes: dict[str, str],
        file_indexes: dict[str, _FileIndex],
    ) -> None:
        self.file_index = file_index
        self.module_paths = module_paths
        self.classes_by_name = classes_by_name
        self.local_classes = local_classes
        self.file_indexes = file_indexes

    def resolve(self, call: ast.Call, enclosing_class: Optional[ast.ClassDef]) -> Optional[str]:
        func = call.func
        if isinstance(func, ast.Attribute):
            return self._resolve_attribute_call(func, enclosing_class)
        if isinstance(func, ast.Name):
            return self._resolve_name_call(func.id)
        return None

    def _resolve_attribute_call(
        self, func: ast.Attribute, enclosing_class: Optional[ast.ClassDef]
    ) -> Optional[str]:
        if not isinstance(func.value, ast.Name):
            return None
        receiver = func.value.id
        method_name = func.attr

        if receiver == "self" and enclosing_class is not None:
            if _class_has_method(enclosing_class, method_name):
                parts = [p for p in (self.file_index.module_qualname, enclosing_class.name, method_name) if p]
                return ".".join(parts)
            return None

        class_name = self.local_classes.get(receiver)
        if class_name is not None:
            return self._method_qualname(class_name, method_name)

        if receiver in self.file_index.import_aliases:
            target_module = self.file_index.import_aliases[receiver]
            return self._function_qualname_in_module(target_module, method_name)

        if receiver in self.file_index.from_imports:
            # `from pkg import sub` then `sub.foo()` — receiver is a module.
            source_module, original = self.file_index.from_imports[receiver]
            full_module = f"{source_module}.{original}" if source_module else original
            return self._function_qualname_in_module(full_module, method_name)

        return None

    def _resolve_name_call(self, name: str) -> Optional[str]:
        if name in self.file_index.top_level_names:
            return f"{self.file_index.module_qualname}.{name}" if self.file_index.module_qualname else name

        if name in self.file_index.from_imports:
            source_module, original = self.file_index.from_imports[name]
            # Could be a class constructor or a function; prefer function.
            return self._function_qualname_in_module(source_module, original)
        return None

    def _method_qualname(self, class_name: str, method_name: str) -> Optional[str]:
        refs = self.classes_by_name.get(class_name) or []
        for ref in refs:
            if _class_has_method(ref.node, method_name):
                return f"{ref.qualname}.{method_name}"
        return None

    def _function_qualname_in_module(self, module: str, name: str) -> Optional[str]:
        path = self.module_paths.get(module)
        if path is None:
            return None
        idx = self.file_indexes.get(path)
        if idx is None:
            return None
        if name in idx.top_level_names:
            return f"{idx.module_qualname}.{name}" if idx.module_qualname else name
        return None


def _class_has_method(cls: ast.ClassDef, method_name: str) -> bool:
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
            return True
    return False


def _direct_calls_in(func_node: ast.AST):
    """Yield ast.Call nodes inside func_node, skipping nested function bodies.

    A nested def gets its own entry in the call graph; we don't want its
    calls double-counted under the enclosing function.
    """
    for child in ast.iter_child_nodes(func_node):
        yield from _walk_excluding_nested_funcs(child)


def _walk_excluding_nested_funcs(node: ast.AST):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        return
    if isinstance(node, ast.Call):
        yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_excluding_nested_funcs(child)
