"""Functions/methods with too many parameters (PoSD §9).

Each parameter pushes uncertainty from the module up to its callers. A function
with many optional parameters is usually a module that didn't want to decide.

Calibration: ≥7 parameters total or ≥5 with default values. The two thresholds
catch slightly different smells:
  - "many params total" suggests the function is doing too much.
  - "many optional params" is the textbook configuration-explosion case —
    the author offering knobs because they couldn't pick defaults.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


TOTAL_PARAM_THRESHOLD = 7
OPTIONAL_PARAM_THRESHOLD = 5


@register
class ConfigExplosionDetector(Detector):
    name = "config_explosion"
    title = "Configuration-parameter explosion"
    rubric_ref = "9"
    rubric_title = "Pull complexity downward"

    def __init__(
        self,
        total_threshold: int = TOTAL_PARAM_THRESHOLD,
        optional_threshold: int = OPTIONAL_PARAM_THRESHOLD,
    ):
        self.total_threshold = total_threshold
        self.optional_threshold = optional_threshold

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = self.function_param_names(node)
            optionals = self.function_default_count(node)
            n_params = len(params)
            if n_params < self.total_threshold and optionals < self.optional_threshold:
                continue
            # Don't double-flag if both thresholds trip; prefer the more pointed one.
            reason = self._reason(n_params, optionals)
            kind = self._kind(node)
            yield Finding(
                file=file.path,
                line=node.lineno,
                detector=self.name,
                title=f"{kind} '{node.name}' has too many parameters",
                evidence=reason,
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.MEDIUM,
                code_excerpt=file.excerpt(node.lineno, node.lineno + 2, context=2),
            )

    def _reason(self, n_params: int, optionals: int) -> str:
        if optionals >= self.optional_threshold and n_params >= self.total_threshold:
            return f"{n_params} parameters, {optionals} optional"
        if optionals >= self.optional_threshold:
            return f"{optionals} optional parameters"
        return f"{n_params} parameters"

    @staticmethod
    def _kind(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        parent = getattr(node, "parent", None)
        if isinstance(parent, ast.ClassDef):
            return "Method" if node.name != "__init__" else "Constructor"
        return "Function"
