"""Promised-pure functions that aren't (PoSD §13).

A function whose name promises pure computation — `calculate_total`,
`parse_response`, `format_date`, `to_json` — should not, in fact, write to
disk, hit the network, or mutate global state. The name is a contract; if
the implementation does I/O the reader who relied on the name is misled.

Detection shape (project-level):
- Project-level because we need `function_effects`, which is built across
  the entire call graph. A per-file detector would only see direct effects,
  missing the case where `calculate_total` calls `_persist_total` which
  writes to disk.
- Heuristic: name starts with a "pure" prefix (calculate_, parse_, to_, ...)
  AND `function_effects[qualname]` is non-empty.

Calibration:
- The prefix list is curated to avoid common false-flags: helpers like
  `print_summary` (which obviously prints) or `save_to_disk` (which obviously
  writes) aren't on the list. Only names that *imply purity*.
"""

from __future__ import annotations

from typing import Iterable

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project


PURE_PREFIXES = (
    "calculate_",
    "compute_",
    "parse_",
    "format_",
    "to_",
    "as_",
    "validate_",
    "derive_",
    "transform_",
    "convert_",
    "normalize_",
    "serialize_",
    "deserialize_",
    "summarize_",
)


@register_project
class PureFunctionViolationDetector(ProjectDetector):
    name = "pure_function_violation"
    title = "Promised-pure function has effects"
    rubric_ref = "13"
    rubric_title = "Choosing names"

    def detect_project(self, project: Project) -> Iterable[Finding]:
        effects = project.function_effects
        if not effects:
            return

        node_lookup = _build_node_lookup(project)

        for qualname, effect_set in effects.items():
            if not effect_set:
                continue
            short_name = qualname.rsplit(".", 1)[-1]
            if not short_name.startswith(PURE_PREFIXES):
                continue
            file_path, line, end_line = node_lookup.get(qualname, (None, 1, 1))
            if file_path is None:
                continue
            evidence = (
                f"name suggests pure computation but propagated effects: "
                f"{', '.join(sorted(effect_set))}"
            )
            yield Finding(
                file=file_path,
                line=line,
                end_line=end_line,
                detector=self.name,
                title=f"'{short_name}' name promises purity but has effects",
                evidence=evidence,
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.MEDIUM,
                code_excerpt=_excerpt(project, file_path, line),
            )


def _build_node_lookup(project: Project) -> dict[str, tuple[str, int, int]]:
    """Map qualname -> (file_path, lineno, end_lineno) for every function/method.

    The call graph yields qualnames but not their AST locations; we walk the
    files once to build this index so each finding can point at the source.
    """
    out: dict[str, tuple[str, int, int]] = {}
    import ast

    for f in project.files:
        module_qual = project._qualname_for(f.path)
        for stmt in f.tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{module_qual}.{stmt.name}" if module_qual else stmt.name
                out[qual] = (f.path, stmt.lineno, getattr(stmt, "end_lineno", stmt.lineno))
            elif isinstance(stmt, ast.ClassDef):
                for item in stmt.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        parts = [p for p in (module_qual, stmt.name, item.name) if p]
                        out[".".join(parts)] = (
                            f.path, item.lineno, getattr(item, "end_lineno", item.lineno),
                        )
    return out


def _excerpt(project: Project, path: str, line: int) -> str:
    for f in project.files:
        if f.path == path:
            end = line + 4
            return f.excerpt(line, end, context=1)
    return ""
