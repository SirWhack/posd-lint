"""Project-level cross-file model.

Phase 1 and 2 detectors operate per-file: they take a ParsedFile and emit
findings. Phase 3 detectors need to know things like "which files import
X", "where else is ClassName.attr read", "what other classes live in this
package". That requires a model built across all files before any detector
runs.

This module is responsible for that. The Project class lazily computes
indexes from a list of ParsedFiles. Indexes are cached on first access —
detectors share the work, and a re-run with the same files is free.

Indexes provided:
- imports_by_file: who imports what, with line numbers.
- classes_by_name: every class definition, with its file and AST node.
- public_class_attributes: per class, the names of public attrs accessed
  on instances of that class anywhere in the project.
- module_paths: maps a module's dotted path back to its source file path,
  so import statements can be resolved.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Optional

from posd_lint._callgraph import (
    CallSite,
    build_call_graph,
    build_call_sites,
    build_external_calls,
)
from posd_lint.effects import compute_function_effects
from posd_lint.parse import ParsedFile


@dataclass
class ImportRef:
    """A single `import X` or `from X import Y` site."""
    file: str
    line: int
    module: str           # the module being imported (`tracker.config` for `from tracker.config import Config`)
    name: str             # the local name brought into scope (`Config` or `tracker` for `import tracker`)
    is_from_import: bool  # True for `from X import Y`, False for `import X`


@dataclass
class ClassRef:
    """A class definition, with the file path that contains it."""
    file: str
    name: str
    qualname: str         # 'tracker.config.Config' (best-effort from file path)
    node: ast.ClassDef
    public_attrs_defined: set[str] = field(default_factory=set)


@dataclass
class AttrAccess:
    """A single `instance.attr` read site for a known class instance."""
    file: str
    line: int
    attr: str
    receiver_name: str    # the local var name through which attr was accessed


@dataclass
class Project:
    """Cross-file model of a Python project.

    Built once per `posd-lint` run. Holds a list of ParsedFiles plus indexes
    derived from them. Detectors that need cross-file context take this
    Project; per-file detectors don't see it.
    """
    files: list[ParsedFile]
    root: Path

    @cached_property
    def imports_by_file(self) -> dict[str, list[ImportRef]]:
        """For every file: each `import X` or `from X import Y` it contains."""
        out: dict[str, list[ImportRef]] = defaultdict(list)
        for f in self.files:
            for node in ast.walk(f.tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        out[f.path].append(ImportRef(
                            file=f.path, line=node.lineno,
                            module=alias.name,
                            name=alias.asname or alias.name.split(".")[0],
                            is_from_import=False,
                        ))
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        if alias.name == "*":
                            continue  # wildcard imports — can't resolve symbols
                        out[f.path].append(ImportRef(
                            file=f.path, line=node.lineno,
                            module=module,
                            name=alias.asname or alias.name,
                            is_from_import=True,
                        ))
        return dict(out)

    @cached_property
    def classes_by_name(self) -> dict[str, list[ClassRef]]:
        """Every class def in the project, keyed by the class's local name.

        A name may map to multiple ClassRefs (the same name defined in
        different modules). Detectors that use this should disambiguate by
        file path or by following imports.
        """
        out: dict[str, list[ClassRef]] = defaultdict(list)
        for f in self.files:
            qualbase = self._qualname_for(f.path)
            for node in ast.walk(f.tree):
                if isinstance(node, ast.ClassDef):
                    qualname = f"{qualbase}.{node.name}" if qualbase else node.name
                    public_attrs = self._public_attrs_defined_in_class(node)
                    out[node.name].append(ClassRef(
                        file=f.path,
                        name=node.name,
                        qualname=qualname,
                        node=node,
                        public_attrs_defined=public_attrs,
                    ))
        return dict(out)

    @cached_property
    def public_class_attributes(self) -> dict[str, list[AttrAccess]]:
        """For each defined class name, every external `instance.attr` access site.

        Entries are keyed by the class's *unqualified* name. We track
        accesses where the receiver was a Name we can confidently match
        back to that class via local imports — function parameters
        annotated `x: ClassName` and assignments `x = ClassName(...)` count
        as confident; deeper inference is out of scope here.
        """
        out: dict[str, list[AttrAccess]] = defaultdict(list)
        defined_class_names = set(self.classes_by_name.keys())

        for f in self.files:
            local_to_class = self._local_var_classes(f, defined_class_names)
            if not local_to_class:
                continue
            for node in ast.walk(f.tree):
                if not isinstance(node, ast.Attribute):
                    continue
                if not isinstance(node.value, ast.Name):
                    continue
                class_name = local_to_class.get(node.value.id)
                if class_name is None:
                    continue
                # Skip private attrs (leading underscore) — we're tracking
                # interface leakage, not implementation leakage.
                if node.attr.startswith("_"):
                    continue
                out[class_name].append(AttrAccess(
                    file=f.path,
                    line=node.lineno,
                    attr=node.attr,
                    receiver_name=node.value.id,
                ))
        return dict(out)

    @cached_property
    def call_graph(self) -> dict[str, set[str]]:
        """Maps qualified caller name -> set of qualified callee names.

        Qualified format: `module.qualname.func_name`, e.g.
        `tracker.agent.TimeTrackingAgent._execute_tool`. Free functions
        appear as `module.func_name`.

        Approximate by design — we only emit edges we can resolve
        confidently (self-calls, calls on locals with known types, calls
        through known imports, bare calls to top-level names in the same
        file). Recall < 1; precision is the priority so detectors built
        on top of this graph don't have to second-guess their evidence.
        """
        return build_call_graph(
            files=self.files,
            qualname_for=self._qualname_for,
            module_paths=self.module_paths,
            classes_by_name=self.classes_by_name,
            local_var_classes_for=lambda f: self._local_var_classes(f, set(self.classes_by_name.keys())),
        )

    @cached_property
    def call_sites(self) -> list[CallSite]:
        """Every resolved call as a CallSite record (caller, callee, ast.Call, file).

        Same resolution rules as `call_graph`; the difference is shape — this
        keeps every call site separate so detectors can inspect arguments at
        the per-call level (e.g. which positional arg carried which param).
        """
        return build_call_sites(
            files=self.files,
            qualname_for=self._qualname_for,
            module_paths=self.module_paths,
            classes_by_name=self.classes_by_name,
            local_var_classes_for=lambda f: self._local_var_classes(f, set(self.classes_by_name.keys())),
        )

    @cached_property
    def external_calls(self) -> dict[str, set[str]]:
        """Maps qualified caller name -> dotted external symbols it invokes.

        "External" = the call target wasn't resolved to a project-internal
        function. Each entry is a best-effort dotted form (`requests.get`,
        `pathlib.Path.read_text`, `print`). Used by `function_effects` to
        consult the curated effect registry.
        """
        return build_external_calls(
            files=self.files,
            qualname_for=self._qualname_for,
            module_paths=self.module_paths,
            classes_by_name=self.classes_by_name,
            local_var_classes_for=lambda f: self._local_var_classes(f, set(self.classes_by_name.keys())),
        )

    @cached_property
    def function_effects(self) -> dict[str, set[str]]:
        """Maps qualified function name -> set of effect category names.

        Categories come from `posd_lint/data/effects.toml`: filesystem,
        network, database, global_state, subprocess, stdout, time, random.
        Effects propagate through `call_graph`: a function's set is its
        direct external-symbol effects ∪ the effects of every function it
        transitively calls. Cyclic call graphs are handled via SCC
        contraction.
        """
        return compute_function_effects(
            call_graph=self.call_graph,
            external_calls=self.external_calls,
            all_functions=self._all_function_qualnames(),
        )

    def _all_function_qualnames(self) -> list[str]:
        """Every function/method's qualified name across the project.

        The call graph only contains functions that make at least one
        resolvable call; the effects layer needs every function so leaves
        (which only call out to externals or do nothing) still appear in
        the output.
        """
        out: list[str] = []
        for f in self.files:
            module_qual = self._qualname_for(f.path)
            for stmt in f.tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual = f"{module_qual}.{stmt.name}" if module_qual else stmt.name
                    out.append(qual)
                elif isinstance(stmt, ast.ClassDef):
                    for item in stmt.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            parts = [p for p in (module_qual, stmt.name, item.name) if p]
                            out.append(".".join(parts))
        return out

    @cached_property
    def module_paths(self) -> dict[str, str]:
        """Maps `tracker.config` -> path/to/tracker/config.py.

        Lets a `from tracker.config import Config` import be resolved back
        to the file that defines `Config`. Best-effort: relies on the file
        being under self.root and having a recognizable package layout.
        """
        out: dict[str, str] = {}
        for f in self.files:
            qual = self._qualname_for(f.path)
            if qual:
                out[qual] = f.path
        return out

    def _qualname_for(self, path: str) -> str:
        """Best-effort dotted module name for a file path.

        Walks parents from the file up to self.root, dropping any segment
        that isn't a valid Python package (no __init__.py needed for our
        purposes — we just want a stable id, not import semantics). The
        last segment is the module name (filename without .py).
        """
        try:
            rel = Path(path).resolve().relative_to(self.root.resolve())
        except ValueError:
            return ""
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]  # strip .py
        # Common src-layout convention: drop a leading 'src' segment.
        if parts and parts[0] == "src":
            parts = parts[1:]
        return ".".join(parts)

    def _public_attrs_defined_in_class(self, cls: ast.ClassDef) -> set[str]:
        """Names that look like public instance/class attributes of cls.

        We look at three sources: class-body assignments (class vars),
        AnnAssign at class scope (annotated class vars), and `self.X = ...`
        inside `__init__` (instance attrs). Private (leading _) excluded.
        """
        attrs: set[str] = set()
        for item in cls.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        attrs.add(target.id)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if not item.target.id.startswith("_"):
                    attrs.add(item.target.id)
            elif isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Assign):
                        for tgt in sub.targets:
                            if (isinstance(tgt, ast.Attribute)
                                and isinstance(tgt.value, ast.Name)
                                and tgt.value.id == "self"
                                and not tgt.attr.startswith("_")):
                                attrs.add(tgt.attr)
        return attrs

    def _local_var_classes(self, f: ParsedFile, known_classes: set[str]) -> dict[str, str]:
        """Map `local_var_name -> class_name` for vars confidently typed in f.

        Confidence sources:
        - Function parameters with annotation `param: ClassName`.
        - Module-level assignments `x = ClassName(...)`.
        - Local assignments `x = ClassName(...)` inside any function.
        - Assignments `x = func()` / `x = obj.method()` where the callee has
          a return-type annotation we can resolve to a known class.
        - For-loop iteration `for x in <expr>` where <expr> is a method call
          whose annotation is `list[ClassName]` (or Iterable/Sequence/tuple
          of ClassName).

        This is a coarse approximation — real type inference would do
        better — but for the leakage detector we want to *miss* uncertain
        cases rather than hallucinate.
        """
        out: dict[str, str] = {}
        return_types = self._function_return_types
        for node in ast.walk(f.tree):
            # `param: ClassName` annotations.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args + node.args.kwonlyargs:
                    if arg.annotation is None:
                        continue
                    cn = self._extract_class_name(arg.annotation)
                    if cn and cn in known_classes:
                        out[arg.arg] = cn
            # `x = ClassName(...)` and `x = callee()` assignments.
            if isinstance(node, ast.Assign):
                cn = self._infer_call_class(node.value, known_classes, return_types)
                if cn:
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            out[tgt.id] = cn
            # `for x in <call>` — iterate over a typed iterable.
            if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
                if isinstance(node.iter, ast.Call):
                    cn = self._return_class_for_call(node.iter, known_classes, return_types)
                    if cn:
                        out[node.target.id] = cn
        return out

    def _infer_call_class(
        self,
        value: Optional[ast.expr],
        known_classes: set[str],
        return_types: dict[str, str],
    ) -> Optional[str]:
        """For `x = <value>`: if value is a recognizable typed call, return its class."""
        if not isinstance(value, ast.Call):
            return None
        # Direct constructor: ClassName(...)
        cn = self._extract_class_name(value.func)
        if cn and cn in known_classes:
            return cn
        return self._return_class_for_call(value, known_classes, return_types)

    def _return_class_for_call(
        self,
        call: ast.Call,
        known_classes: set[str],
        return_types: dict[str, str],
    ) -> Optional[str]:
        """If `call` resolves to a function with a known return-type, return its class.

        We index callables by their unqualified function/method name. That
        creates collisions across classes — but for the leakage detector
        precision-on-name is enough: if every `list_orders` in the project
        returns `list[Order]`, we're safe. When the index disagrees, we
        bail and return None rather than picking arbitrarily.
        """
        func = call.func
        if isinstance(func, ast.Name):
            key = func.id
        elif isinstance(func, ast.Attribute):
            key = func.attr
        else:
            return None
        cn = return_types.get(key)
        if cn and cn in known_classes:
            return cn
        return None

    @cached_property
    def _function_return_types(self) -> dict[str, str]:
        """Index `function/method short-name -> return-type ClassName`.

        Built once across all files. Conflicts (same name, different
        return types) collapse to None and are dropped from the index —
        better to miss a binding than to claim a wrong one.
        """
        candidates: dict[str, set[str]] = defaultdict(set)
        for f in self.files:
            for node in ast.walk(f.tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns is None:
                        continue
                    cn = self._extract_class_name(node.returns)
                    if cn:
                        candidates[node.name].add(cn)
        return {name: next(iter(cns)) for name, cns in candidates.items() if len(cns) == 1}

    @staticmethod
    def _extract_class_name(node: ast.expr) -> Optional[str]:
        """Pull the rightmost name out of `ClassName`, `mod.ClassName`,
        `Optional[ClassName]`, `list[ClassName]`. Returns None for anything
        we can't read confidently."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Subscript):
            return Project._extract_class_name(node.slice)
        return None


def build_project(files: list[ParsedFile], root: Path) -> Project:
    """Convenience constructor — keeps detector code from importing dataclasses."""
    return Project(files=files, root=root)
