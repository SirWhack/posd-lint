"""High fan-in classes used directly without an interface boundary (PoSD §5).

A concrete class imported by ten-plus files is a de facto interface — every
caller is coupled to its current shape, and a signature change ripples across
the project. The defensive move is to introduce a Protocol/ABC and let callers
depend on that, leaving the concrete class free to evolve.

Detection shape (project-level):
- Count distinct importers per top-level class name (matched via the local
  name brought into scope by `from X import Name` or `import Name`).
- A class is "behind an interface" if any of its bases looks like one
  (`Protocol`, `ABC`, or any name ending in `ABC` — crude but matches the
  conventions we see in practice).
- Flag any class with importers >= IMPORTER_THRESHOLD that isn't behind one.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Iterable, TYPE_CHECKING

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project

if TYPE_CHECKING:
    from posd_lint.config import Config


IMPORTER_THRESHOLD = 10


@register_project
class UnstableInterfaceDetector(ProjectDetector):
    name = "unstable_interface"
    title = "Concrete class used as a wide interface"
    rubric_ref = "5"
    rubric_title = "Deep vs. shallow modules"

    def __init__(
        self,
        threshold: int = IMPORTER_THRESHOLD,
        config: "Config | None" = None,
    ) -> None:
        self._threshold = threshold

    def detect_project(self, project: Project) -> Iterable[Finding]:
        importers: dict[str, set[str]] = defaultdict(set)
        for path, refs in project.imports_by_file.items():
            for ref in refs:
                importers[ref.name].add(path)

        for class_name, defs in project.classes_by_name.items():
            count = len(importers.get(class_name, ()))
            if count < self._threshold:
                continue
            for cls_ref in defs:
                if _has_interface_base(cls_ref.node):
                    continue
                yield Finding(
                    file=cls_ref.file,
                    line=cls_ref.node.lineno,
                    detector=self.name,
                    title=f"Class '{class_name}' has {count} importers without a Protocol/ABC",
                    evidence=(
                        f"{count} files import '{class_name}' directly; "
                        f"no Protocol/ABC base on the class definition"
                    ),
                    rubric_ref=self.rubric_ref,
                    rubric_title=self.rubric_title,
                    severity=Severity.LOW,
                    code_excerpt=_excerpt(project, cls_ref.file, cls_ref.node.lineno),
                )


def _has_interface_base(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = _base_name(base)
        if name is None:
            continue
        if name == "Protocol" or name == "ABC" or name.endswith("ABC"):
            return True
    return False


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


def _excerpt(project: Project, path: str, line: int) -> str:
    for f in project.files:
        if f.path == path:
            return f.excerpt(line, line + 2, context=1)
    return ""
