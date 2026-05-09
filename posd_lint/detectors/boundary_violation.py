"""Layer boundary violations — domain reaching into infra, etc. (PoSD §6, §8).

Layered architectures encode an explicit dependency direction: domain doesn't
know about infrastructure, infrastructure may depend on domain. The user
declares layer membership via path globs and the allowed direction via
`[allowed_imports]`. Anything else is a boundary violation.

Detection shape (project-level):
- Classify each file into a layer (first matching glob wins; unscoped files
  are skipped — only declared layers are policed).
- For each in-project import, classify the imported module's file into a layer.
- If the importer's layer doesn't list the importee's layer in its allowed
  set, flag. Same-layer imports are always allowed.
- Imports we can't resolve to a project file (stdlib, third-party, or the
  module simply isn't part of any declared layer) are skipped.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project

if TYPE_CHECKING:
    from posd_lint.config import Config


@register_project
class BoundaryViolationDetector(ProjectDetector):
    name = "boundary_violation"
    title = "Layer boundary violation"
    rubric_ref = "6"
    rubric_title = "Information hiding (and leakage)"

    def __init__(self, config: "Config | None" = None) -> None:
        self._layers: dict[str, list[str]] = (
            dict(config.layers) if config is not None else {}
        )
        self._allowed: dict[str, list[str]] = (
            dict(config.allowed_imports) if config is not None else {}
        )

    def detect_project(self, project: Project) -> Iterable[Finding]:
        if not self._layers:
            return
        root = project.root.resolve()
        module_to_path = project.module_paths

        file_layer: dict[str, str] = {}
        for f in project.files:
            rel = _relative_posix(f.path, root)
            if rel is None:
                continue
            layer = _layer_for(rel, self._layers)
            if layer is not None:
                file_layer[f.path] = layer

        for src, refs in project.imports_by_file.items():
            src_layer = file_layer.get(src)
            if src_layer is None:
                continue
            allowed = set(self._allowed.get(src_layer, []))
            for ref in refs:
                target_path = _resolve_import(ref, module_to_path)
                if target_path is None or target_path == src:
                    continue
                target_layer = file_layer.get(target_path)
                if target_layer is None or target_layer == src_layer:
                    continue
                if target_layer in allowed:
                    continue
                yield Finding(
                    file=src,
                    line=ref.line,
                    detector=self.name,
                    title=(
                        f"Layer '{src_layer}' imports '{target_layer}' "
                        f"(not allowed)"
                    ),
                    evidence=(
                        f"'{ref.module}' resolves into layer '{target_layer}'; "
                        f"'{src_layer}' allows: "
                        f"{sorted(allowed) if allowed else 'none'}"
                    ),
                    rubric_ref=self.rubric_ref,
                    rubric_title=self.rubric_title,
                    severity=Severity.MEDIUM,
                    code_excerpt=_excerpt(project, src, ref.line),
                )


def _relative_posix(path: str, root: Path) -> str | None:
    try:
        rel = Path(path).resolve().relative_to(root)
    except ValueError:
        return None
    return rel.as_posix()


def _layer_for(rel_path: str, layers: dict[str, list[str]]) -> str | None:
    for layer, patterns in layers.items():
        for pattern in patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return layer
    return None


def _resolve_import(ref, module_to_path: dict[str, str]) -> str | None:
    """Mirror import_cycle's resolution: try whole module, then submodule for from-imports."""
    target = module_to_path.get(ref.module)
    if target is None and ref.is_from_import and ref.module:
        target = module_to_path.get(f"{ref.module}.{ref.name}")
    if target is None and not ref.is_from_import:
        target = module_to_path.get(ref.name)
    return target


def _excerpt(project: Project, path: str, line: int) -> str:
    for f in project.files:
        if f.path == path:
            return f.excerpt(line, line, context=1)
    return ""
