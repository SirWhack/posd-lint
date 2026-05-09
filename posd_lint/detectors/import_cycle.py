"""Circular imports — files that depend on each other transitively (PoSD §6).

A cycle in the import graph means two or more modules can't be understood (or
loaded) in isolation: each one's interface depends on knowledge of the others.
That's textbook information leakage — the same design decision is smeared
across files that pretend to be separate, and you can't change one without
walking the loop.

Detection shape (project-level):
- Build a directed graph file -> {files it imports} by resolving each import's
  module via `Project.module_paths`. Imports that don't resolve inside the
  project (stdlib, third-party) are dropped.
- Run Tarjan's SCC. Any SCC of size >= 2 is a cycle; self-loops are ignored.
- Emit one Finding per cycle, anchored at the alphabetically smallest file in
  the SCC, with the rest listed in `evidence`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project


@register_project
class ImportCycleDetector(ProjectDetector):
    name = "import_cycle"
    title = "Import cycle"
    rubric_ref = "6"
    rubric_title = "Information hiding (and leakage)"

    def detect_project(self, project: Project) -> Iterable[Finding]:
        graph = self._build_graph(project)
        for scc in self._tarjan_scc(graph):
            if len(scc) < 2:
                continue
            members = sorted(scc)
            anchor = members[0]
            others = members[1:]
            yield Finding(
                file=anchor,
                line=1,
                detector=self.name,
                title=f"Import cycle across {len(members)} files",
                evidence=f"cycle members: {', '.join(others)}",
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.MEDIUM,
                code_excerpt="  cycle: " + " -> ".join(members + [anchor]),
            )

    @staticmethod
    def _build_graph(project: Project) -> dict[str, set[str]]:
        module_to_path = project.module_paths
        graph: dict[str, set[str]] = defaultdict(set)
        for f in project.files:
            graph.setdefault(f.path, set())
        for src, refs in project.imports_by_file.items():
            for ref in refs:
                # `from pkg.mod import name` resolves first against `pkg.mod`
                # (whole module) and falls back to `pkg.mod.name` (submodule).
                target_path = module_to_path.get(ref.module)
                if target_path is None and ref.is_from_import and ref.module:
                    target_path = module_to_path.get(f"{ref.module}.{ref.name}")
                if target_path is None:
                    target_path = module_to_path.get(ref.name) if not ref.is_from_import else None
                if target_path and target_path != src:
                    graph[src].add(target_path)
        return graph

    @staticmethod
    def _tarjan_scc(graph: dict[str, set[str]]) -> list[list[str]]:
        """Iterative Tarjan's SCC. Recursive form blows the stack on big graphs."""
        index_of: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        sccs: list[list[str]] = []
        counter = 0

        for start in graph:
            if start in index_of:
                continue
            # work stack entries: (node, iterator over successors)
            work: list[tuple[str, "_Iter"]] = [(start, _Iter(iter(sorted(graph[start]))))]
            index_of[start] = counter
            lowlink[start] = counter
            counter += 1
            stack.append(start)
            on_stack.add(start)

            while work:
                node, it = work[-1]
                next_succ = it.next_or_none()
                if next_succ is None:
                    if lowlink[node] == index_of[node]:
                        component: list[str] = []
                        while True:
                            popped = stack.pop()
                            on_stack.discard(popped)
                            component.append(popped)
                            if popped == node:
                                break
                        sccs.append(component)
                    work.pop()
                    if work:
                        parent = work[-1][0]
                        lowlink[parent] = min(lowlink[parent], lowlink[node])
                    continue

                if next_succ not in index_of:
                    index_of[next_succ] = counter
                    lowlink[next_succ] = counter
                    counter += 1
                    stack.append(next_succ)
                    on_stack.add(next_succ)
                    work.append((next_succ, _Iter(iter(sorted(graph.get(next_succ, set()))))))
                elif next_succ in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[next_succ])

        return sccs


class _Iter:
    """Tiny wrapper so we can peek-style consume successors in the work loop."""
    __slots__ = ("_it",)

    def __init__(self, it):
        self._it = it

    def next_or_none(self):
        return next(self._it, None)
