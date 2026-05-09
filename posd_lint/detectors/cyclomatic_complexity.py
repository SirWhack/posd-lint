"""High cyclomatic complexity (PoSD §17 — Code should be obvious).

McCabe cyclomatic complexity counts the linearly-independent paths through
a function. Once a function exceeds ~10 paths a reader's first guess at its
behaviour starts to fail systematically: there are too many branches to hold
in working memory. That's exactly the obscurity §17 warns against.

Counted constructs (each adds 1 to the base of 1):
- if / elif (each elif is its own branch in ast.If chains)
- for / async for / while
- except handlers (one per `except` clause)
- and / or (each short-circuit operand beyond the first)
- assert
- comprehension `if` filters
- match cases (one per `case`)

Severity is bucketed because a 12-path function is annoying but a 30-path
function is a different category of problem entirely.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


THRESHOLD_LOW = 10
THRESHOLD_MEDIUM = 15
THRESHOLD_HIGH = 20


@register
class CyclomaticComplexityDetector(Detector):
    name = "cyclomatic_complexity"
    title = "High cyclomatic complexity"
    rubric_ref = "17"
    rubric_title = "Code should be obvious"

    def __init__(
        self,
        threshold_low: int = THRESHOLD_LOW,
        threshold_medium: int = THRESHOLD_MEDIUM,
        threshold_high: int = THRESHOLD_HIGH,
    ) -> None:
        self.threshold_low = threshold_low
        self.threshold_medium = threshold_medium
        self.threshold_high = threshold_high

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            score = self._complexity(node)
            if score < self.threshold_low:
                continue
            severity = self._severity_for(score)
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            yield Finding(
                file=file.path,
                line=node.lineno,
                detector=self.name,
                title=f"Function '{node.name}' has cyclomatic complexity {score}",
                evidence=(
                    f"McCabe complexity {score} (threshold {self.threshold_low}); "
                    f"a reader cannot hold this many branches in working memory"
                ),
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=severity,
                end_line=end,
                code_excerpt=file.excerpt(node.lineno, min(end, node.lineno + 6), context=1),
            )

    def _severity_for(self, score: int) -> Severity:
        if score >= self.threshold_high:
            return Severity.HIGH
        if score >= self.threshold_medium:
            return Severity.MEDIUM
        return Severity.LOW

    def _complexity(self, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        score = 1
        for node in ast.walk(fn):
            # Don't count branches in nested function definitions; they get
            # their own finding when ast.walk reaches them at the module level.
            if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            score += _node_contribution(node)
        return score


def _node_contribution(node: ast.AST) -> int:
    if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Assert)):
        return 1
    if isinstance(node, ast.ExceptHandler):
        return 1
    if isinstance(node, ast.BoolOp):
        # `a and b and c` is two branches beyond the base, not one.
        return max(0, len(node.values) - 1)
    if isinstance(node, ast.comprehension):
        return len(node.ifs)
    if isinstance(node, ast.match_case):
        return 1
    return 0
