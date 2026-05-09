"""Detector base classes + registry.

Two flavors:
- Detector: per-file. Receives a single ParsedFile.
- ProjectDetector: cross-file. Receives the whole Project.

Both register into separate lists so the orchestrator can run each in turn.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from typing import Iterable, TYPE_CHECKING

from posd_lint.findings import Finding
from posd_lint.parse import ParsedFile

if TYPE_CHECKING:
    from posd_lint.project import Project


# Populated by @register / @register_project on each subclass at import time.
DETECTORS: list[type[Detector]] = []
PROJECT_DETECTORS: list[type[ProjectDetector]] = []


def register(cls: type[Detector]) -> type[Detector]:
    """Class decorator: register a per-file Detector subclass for discovery."""
    DETECTORS.append(cls)
    return cls


def register_project(cls: type[ProjectDetector]) -> type[ProjectDetector]:
    """Class decorator: register a project-level Detector subclass for discovery."""
    PROJECT_DETECTORS.append(cls)
    return cls


class Detector(ABC):
    """A deterministic detector for one PoSD red flag.

    Subclasses set name/title/rubric_ref as class attributes and implement
    detect(). Thresholds live as class-level defaults that can be overridden
    by the constructor — keeps subclasses tunable without touching their code.
    """

    name: str            # stable id, used in CLI flags and reports
    title: str           # short human title
    rubric_ref: str      # section number in posd-reference.md (e.g. "5")
    rubric_title: str    # human title of that section

    @abstractmethod
    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        """Yield Findings for this detector's red flag in the given file."""

    @staticmethod
    def is_public(name: str) -> bool:
        """Convention: leading underscore = private. Dunder methods aren't 'public API'."""
        return not name.startswith("_")

    @staticmethod
    def function_param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """All positional/keyword arg names, excluding self/cls."""
        args = node.args
        names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
        return [n for n in names if n not in ("self", "cls")]

    @staticmethod
    def function_default_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """Count of args that have default values (positional + keyword-only)."""
        return len(node.args.defaults) + sum(1 for d in node.args.kw_defaults if d is not None)


class ProjectDetector(ABC):
    """A detector that needs a project-wide model.

    Same name/title/rubric_ref shape as Detector — interchangeable from the
    report's perspective. The CLI orchestrator dispatches to detect_project()
    after building the Project; per-file detect() is not called.
    """

    name: str
    title: str
    rubric_ref: str
    rubric_title: str

    @abstractmethod
    def detect_project(self, project: Project) -> Iterable[Finding]:
        """Yield Findings from cross-file analysis."""

    @staticmethod
    def is_public(name: str) -> bool:
        return not name.startswith("_")
