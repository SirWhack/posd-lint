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

        This is a coarse approximation — real type inference would do
        better — but for the leakage detector we want to *miss* uncertain
        cases rather than hallucinate.
        """
        out: dict[str, str] = {}
        for node in ast.walk(f.tree):
            # `param: ClassName` annotations.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args + node.args.kwonlyargs:
                    if arg.annotation is None:
                        continue
                    cn = self._extract_class_name(arg.annotation)
                    if cn and cn in known_classes:
                        out[arg.arg] = cn
            # `x = ClassName(...)` assignments.
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    cn = self._extract_class_name(node.value.func)
                    if cn and cn in known_classes:
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name):
                                out[tgt.id] = cn
        return out

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
