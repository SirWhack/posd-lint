"""Modules that expose far more than any single caller needs (PoSD §5, §6).

Ousterhout: 'overexposure — the API for a commonly-used feature forces users
to learn about other features that are rarely used.' A module that exports 20
symbols where every importer touches just 1-2 of them is a kitchen sink:
readers must scan past the noise to find what they need, and renames or
deprecations have to coordinate across many unrelated callers.

Detection shape (project-level):
- Count public symbols defined per module (top-level classes/functions/constants
  whose names don't start with _ and which aren't re-exports).
- Count distinct symbols each importer pulls via `from X import ...`.
- If a module exports ≥THRESHOLD_EXPOSED symbols and the average importer
  pulls ≤THRESHOLD_USED of them, flag the module.

We deliberately don't flag modules with few importers — overexposure is a
problem only if the asymmetry is paid by multiple callers.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Iterable

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project


THRESHOLD_EXPOSED = 10        # module exports at least this many public symbols
THRESHOLD_AVG_USED = 2.0      # but average importer uses at most this many
MIN_IMPORTERS = 3             # need a few importers; one importer is just coupling


@register_project
class OverexposureDetector(ProjectDetector):
    name = "overexposure"
    title = "Module exposes more than callers use"
    rubric_ref = "5"
    rubric_title = "Deep vs. shallow modules"

    def detect_project(self, project: Project) -> Iterable[Finding]:
        # Map: module qualname -> set of public symbol names defined there.
        exposed: dict[str, set[str]] = {}
        for f in project.files:
            qual = project._qualname_for(f.path)
            if not qual:
                continue
            exposed[qual] = self._public_symbols(f.tree)

        # Map: module qualname -> list of (importer_path, set_of_used_symbols).
        used_per_importer: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for path, refs in project.imports_by_file.items():
            for ref in refs:
                if not ref.is_from_import:
                    continue
                if ref.module not in exposed:
                    continue
                used_per_importer[ref.module][path].add(ref.name)

        for module_qual, exports in exposed.items():
            if len(exports) < THRESHOLD_EXPOSED:
                continue
            importers = used_per_importer.get(module_qual, {})
            if len(importers) < MIN_IMPORTERS:
                continue
            avg_used = sum(len(s) for s in importers.values()) / len(importers)
            if avg_used > THRESHOLD_AVG_USED:
                continue
            module_path = project.module_paths.get(module_qual, "")
            if not module_path:
                continue
            yield Finding(
                file=module_path,
                line=1,
                detector=self.name,
                title=f"Module '{module_qual}' is overexposed",
                evidence=(
                    f"exports {len(exports)} public symbols; "
                    f"{len(importers)} importers use {avg_used:.1f} on average"
                ),
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.LOW,
                code_excerpt=f"  exposed: {', '.join(sorted(exports))}",
            )

    @staticmethod
    def _public_symbols(tree: ast.Module) -> set[str]:
        """Top-level public names defined in a module.

        Counts class defs, function defs, and module-level assignments to
        plain Names. Excludes underscore-prefixed names and __all__.
        """
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                names.add(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and not tgt.id.startswith("_"):
                        names.add(tgt.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if not node.target.id.startswith("_"):
                    names.add(node.target.id)
        return names
