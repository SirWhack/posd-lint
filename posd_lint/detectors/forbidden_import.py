"""Forbidden imports — files in a path glob must not import banned modules (PoSD §6).

Architecture rules expressed declaratively: a domain layer should never reach
for `sqlalchemy`, a CLI helper should never import `requests`. The user encodes
those rules in `posd-lint.toml` under `[forbidden_imports]` as `glob -> [modules]`.

Detection shape (project-level):
- For each `glob -> forbidden` pair, walk every file whose project-relative path
  matches the glob, then walk that file's imports. Flag any import whose module
  starts with one of the forbidden names (`sqlalchemy.orm` matches `sqlalchemy`).
- One finding per (file, import-site). Severity medium — these are explicit
  user-declared violations, not heuristic smells.
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
class ForbiddenImportDetector(ProjectDetector):
    name = "forbidden_import"
    title = "Forbidden import"
    rubric_ref = "6"
    rubric_title = "Information hiding (and leakage)"

    def __init__(self, config: "Config | None" = None) -> None:
        self._rules: dict[str, list[str]] = (
            dict(config.forbidden_imports) if config is not None else {}
        )

    def detect_project(self, project: Project) -> Iterable[Finding]:
        if not self._rules:
            return
        root = project.root.resolve()
        for path, refs in project.imports_by_file.items():
            rel = _relative_posix(path, root)
            if rel is None:
                continue
            forbidden = _forbidden_names_for(rel, self._rules)
            if not forbidden:
                continue
            for ref in refs:
                hit = _matched_forbidden(ref.module, forbidden)
                if hit is None:
                    continue
                yield Finding(
                    file=path,
                    line=ref.line,
                    detector=self.name,
                    title=f"Forbidden import '{ref.module}' in {rel}",
                    evidence=(
                        f"file matches forbidden-import rule banning '{hit}'"
                    ),
                    rubric_ref=self.rubric_ref,
                    rubric_title=self.rubric_title,
                    severity=Severity.MEDIUM,
                    code_excerpt=_excerpt(project, path, ref.line),
                )


def _relative_posix(path: str, root: Path) -> str | None:
    try:
        rel = Path(path).resolve().relative_to(root)
    except ValueError:
        return None
    return rel.as_posix()


def _forbidden_names_for(rel_path: str, rules: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for pattern, names in rules.items():
        if fnmatch.fnmatch(rel_path, pattern):
            out.extend(names)
    return out


def _matched_forbidden(module: str, forbidden: list[str]) -> str | None:
    for name in forbidden:
        if module == name or module.startswith(name + "."):
            return name
    return None


def _excerpt(project: Project, path: str, line: int) -> str:
    for f in project.files:
        if f.path == path:
            return f.excerpt(line, line, context=1)
    return ""
