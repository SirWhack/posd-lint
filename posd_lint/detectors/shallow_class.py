"""Classes whose interface is wide relative to the functionality they hide (PoSD §5).

Two patterns flagged here:

1. Pass-through subclass — class body has nothing meaningful (a docstring,
   maybe a single `pass` or trivial constructor that just calls super).
   `SQLiteStore(Repository)` in the time-tracker codebase is the canonical
   case: 3 lines, pure rename of the parent.

2. Shallow class — the body-token count across all method bodies is small
   compared to the interface size (number of public methods + parameters).
   The class isn't hiding anything; you could inline its methods at no
   cognitive cost.

The judge will get a final say — some shallow classes are deliberate (DTOs,
sentinel types), and the rubric section walks Claude through that distinction.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


# Statements-per-public-method threshold. Counts all ast.stmt nodes inside
# each public method body (walked recursively, so a for+try counts everything
# inside it). If the class averages fewer than this many statements per
# public method, it's not hiding much.
BODY_NODES_PER_METHOD_THRESHOLD = 4

# Decorators that exempt a class — a dataclass with many fields and few
# methods is fine; that's the point. Same for Enums and TypedDicts (those
# don't reach here usually but be safe).
EXEMPT_DECORATORS = {"dataclass", "dataclasses.dataclass", "frozen_dataclass", "attrs", "attr.s", "define"}

# Base classes that exempt a class from "shallow" analysis. Subclassing
# Exception/Enum/TypedDict and adding nothing is a legitimate pattern.
EXEMPT_BASES = {"Exception", "BaseException", "Enum", "IntEnum", "StrEnum", "TypedDict", "NamedTuple", "Protocol"}


@register
class ShallowClassDetector(Detector):
    name = "shallow_class"
    title = "Shallow or pass-through class"
    rubric_ref = "5"
    rubric_title = "Deep vs. shallow modules"

    def __init__(self, body_per_method: int = BODY_NODES_PER_METHOD_THRESHOLD):
        self.body_per_method = body_per_method

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if self._is_exempt(node):
                continue

            pass_through = self._pass_through_finding(file, node)
            if pass_through is not None:
                yield pass_through
                continue  # don't double-flag

            shallow = self._shallow_finding(file, node)
            if shallow is not None:
                yield shallow

    def _is_exempt(self, node: ast.ClassDef) -> bool:
        # Decorator-based exemption (dataclass etc.)
        for dec in node.decorator_list:
            name = self._decorator_name(dec)
            if name in EXEMPT_DECORATORS:
                return True
        # Base-class exemption (Exception, Enum, Protocol, TypedDict, etc.)
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in EXEMPT_BASES:
                return True
            if isinstance(base, ast.Attribute) and base.attr in EXEMPT_BASES:
                return True
        return False

    def _pass_through_finding(self, file: ParsedFile, node: ast.ClassDef) -> Finding | None:
        """Detect a class that exists only to rename its parent.

        Heuristic: subclasses exactly one base, has at most a docstring and
        an optional `pass`, no methods or attributes of its own.
        """
        if len(node.bases) != 1:
            return None
        meaningful = [b for b in node.body if not (
            isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str)
        )]
        # Strip a trailing `pass` if present.
        meaningful = [b for b in meaningful if not isinstance(b, ast.Pass)]
        if meaningful:
            return None

        base_name = self._base_name(node.bases[0])
        return Finding(
            file=file.path,
            line=node.lineno,
            detector=self.name,
            title=f"Class '{node.name}' is a pass-through alias of '{base_name}'",
            evidence=f"class body is empty; subclasses {base_name} and adds nothing",
            rubric_ref=self.rubric_ref,
            rubric_title=self.rubric_title,
            severity=Severity.MEDIUM,
            end_line=node.end_lineno,
            code_excerpt=file.excerpt(node.lineno, node.end_lineno or node.lineno, context=2),
        )

    def _shallow_finding(self, file: ParsedFile, node: ast.ClassDef) -> Finding | None:
        """Detect a class whose body is small relative to its public surface.

        Counts AST nodes inside method bodies (depth-1 statements, not full
        walk — full walk overcounts trivial expressions). Excludes the
        method's own docstring statement.
        """
        public_methods = [
            b for b in node.body
            if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
            and self.is_public(b.name) and not b.name.startswith("__")
        ]
        if len(public_methods) < 2:
            return None  # too small to evaluate; let other detectors handle it

        # Walk every statement inside each public method's body (excluding
        # the docstring). A `for` loop with three nested statements counts
        # as four — the loop itself plus its three children.
        total_stmts = 0
        for m in public_methods:
            body = m.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            for stmt in body:
                total_stmts += sum(1 for n in ast.walk(stmt) if isinstance(n, ast.stmt))

        avg = total_stmts / max(len(public_methods), 1)
        if avg >= self.body_per_method:
            return None

        return Finding(
            file=file.path,
            line=node.lineno,
            detector=self.name,
            title=f"Class '{node.name}' is shallow",
            evidence=f"{len(public_methods)} public methods averaging {avg:.1f} body statements each",
            rubric_ref=self.rubric_ref,
            rubric_title=self.rubric_title,
            severity=Severity.MEDIUM,
            end_line=node.end_lineno,
            code_excerpt=file.excerpt(node.lineno, min((node.end_lineno or node.lineno), node.lineno + 30), context=0),
        )

    @staticmethod
    def _decorator_name(dec: ast.expr) -> str:
        if isinstance(dec, ast.Name):
            return dec.id
        if isinstance(dec, ast.Attribute):
            return dec.attr
        if isinstance(dec, ast.Call):
            return ShallowClassDetector._decorator_name(dec.func)
        return ""

    @staticmethod
    def _base_name(base: ast.expr) -> str:
        if isinstance(base, ast.Name):
            return base.id
        if isinstance(base, ast.Attribute):
            return base.attr
        return "<base>"
