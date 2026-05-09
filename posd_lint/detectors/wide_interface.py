"""Classes/Protocols whose public surface spans multiple distinct concerns (PoSD §5, §6).

Inverse of shallow_class: instead of "interface too wide for the body," this
detector flags "interface too wide for any single coherent abstraction." A
20-method Protocol almost certainly bundles three or four design decisions
that would each be a deeper module on its own.

Calibrated for Python: ≥12 public methods is the default threshold. The judge
gets the method names and decides whether they cluster around one abstraction
(library facade — fine) or several (split candidate).
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


PUBLIC_METHOD_THRESHOLD = 12

# These bases tolerate wider interfaces — frameworks need them. The judge
# will still review them via the AI layer if explicitly requested, but the
# default deterministic pass treats them as expected-wide.
EXEMPT_BASES = {"TestCase", "BaseTestCase", "TeamsActivityHandler", "ActivityHandler"}


@register
class WideInterfaceDetector(Detector):
    name = "wide_interface"
    title = "Interface too wide for one abstraction"
    rubric_ref = "5"
    rubric_title = "Deep vs. shallow modules"

    def __init__(self, threshold: int = PUBLIC_METHOD_THRESHOLD):
        self.threshold = threshold

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if self._is_exempt(node):
                continue
            public_methods = [
                b for b in node.body
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
                and self.is_public(b.name) and not b.name.startswith("__")
            ]
            if len(public_methods) < self.threshold:
                continue
            method_names = [m.name for m in public_methods]
            yield Finding(
                file=file.path,
                line=node.lineno,
                detector=self.name,
                title=f"Class '{node.name}' has {len(public_methods)} public methods",
                evidence=f"methods: {', '.join(method_names)}",
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.MEDIUM,
                end_line=node.end_lineno,
                code_excerpt=file.excerpt(node.lineno, node.lineno + 5, context=0),
            )

    def _is_exempt(self, node: ast.ClassDef) -> bool:
        for base in node.bases:
            name = self._base_name(base)
            if name in EXEMPT_BASES:
                return True
        return False

    @staticmethod
    def _base_name(base: ast.expr) -> str:
        if isinstance(base, ast.Name):
            return base.id
        if isinstance(base, ast.Attribute):
            return base.attr
        return ""
