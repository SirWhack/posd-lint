"""Variables that change kind mid-scope (PoSD §13, §17).

Ousterhout: 'repurposed variable — one name, two meanings within a scope.'
A reader who sees `result = []` early in a function and `result = {}` later
has to backtrack and revise their model of `result` — exactly the obscurity
the rubric warns against.

Detection shape — conservative, with shallow type inference:
- Track each Assign target Name within a single function body.
- Infer 'kind' from the RHS using a small, exact set of literal/constructor
  patterns. Anything we can't classify is recorded as UNKNOWN and won't
  contribute to a finding.
- If the same name is later assigned with a *different* known kind, flag.

We deliberately don't try to handle:
- Augmented assignment (`x += 1`) — kind is preserved.
- Reassignment within branches (`if cond: x = []  else: x = {}`) — that's
  parallel construction, often the right pattern; only sequential repurpose
  in straight-line code is flagged.
- None-init pattern (`x = None ... x = compute()`) — common Python idiom.
"""

from __future__ import annotations

import ast
from typing import Iterable, Optional

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


# Kinds we can reliably infer from a literal RHS or a small set of constructor calls.
# UNKNOWN is the default when the inference doesn't apply; UNKNOWN never triggers
# a flag — only same-name reassignment with two *different known* kinds does.
KIND_LIST = "list"
KIND_DICT = "dict"
KIND_SET = "set"
KIND_TUPLE = "tuple"
KIND_STR = "str"
KIND_INT = "int"
KIND_FLOAT = "float"
KIND_BOOL = "bool"
KIND_NONE = "none"
KIND_UNKNOWN = "unknown"

CONSTRUCTOR_KINDS = {
    "list": KIND_LIST, "dict": KIND_DICT, "set": KIND_SET, "tuple": KIND_TUPLE,
    "str": KIND_STR, "int": KIND_INT, "float": KIND_FLOAT, "bool": KIND_BOOL,
    "frozenset": KIND_SET,
}


@register
class RepurposedVariableDetector(Detector):
    name = "repurposed_variable"
    title = "Variable reused for a different kind of value"
    rubric_ref = "13"
    rubric_title = "Choosing names"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            yield from self._detect_in_function(file, node)

    def _detect_in_function(
        self, file: ParsedFile, fn: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> Iterable[Finding]:
        # Track first-seen kind per name. Flag at most once per name per function.
        first_kind: dict[str, str] = {}
        first_line: dict[str, int] = {}
        flagged: set[str] = set()

        # Walk only top-level statements — branched/nested reassignments are
        # too noisy to flag without proper control-flow analysis.
        for stmt in fn.body:
            if not isinstance(stmt, ast.Assign):
                continue
            kind = self._infer_kind(stmt.value)
            if kind == KIND_UNKNOWN or kind == KIND_NONE:
                # None-init pattern: don't seed first_kind from None.
                continue
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name in flagged:
                    continue
                prev = first_kind.get(name)
                if prev is None:
                    first_kind[name] = kind
                    first_line[name] = stmt.lineno
                    continue
                if prev == kind:
                    continue
                flagged.add(name)
                yield Finding(
                    file=file.path,
                    line=first_line[name],
                    detector=self.name,
                    title=f"Variable '{name}' is reused as a different kind of value",
                    evidence=(
                        f"first assigned as {prev} at line {first_line[name]}, "
                        f"then as {kind} at line {stmt.lineno}"
                    ),
                    rubric_ref=self.rubric_ref,
                    rubric_title=self.rubric_title,
                    severity=Severity.LOW,
                    end_line=stmt.lineno,
                    code_excerpt=file.excerpt(first_line[name], stmt.lineno, context=1),
                )

    @staticmethod
    def _infer_kind(node: ast.expr) -> str:
        """Best-effort, side-effect-free kind inference."""
        if isinstance(node, ast.List):
            return KIND_LIST
        if isinstance(node, ast.Dict):
            return KIND_DICT
        if isinstance(node, ast.Set):
            return KIND_SET
        if isinstance(node, ast.Tuple):
            return KIND_TUPLE
        if isinstance(node, ast.Constant):
            value = node.value
            if value is None:
                return KIND_NONE
            if isinstance(value, bool):
                return KIND_BOOL
            if isinstance(value, int):
                return KIND_INT
            if isinstance(value, float):
                return KIND_FLOAT
            if isinstance(value, str):
                return KIND_STR
            return KIND_UNKNOWN
        if isinstance(node, ast.JoinedStr):
            return KIND_STR
        if isinstance(node, ast.ListComp):
            return KIND_LIST
        if isinstance(node, ast.DictComp):
            return KIND_DICT
        if isinstance(node, ast.SetComp):
            return KIND_SET
        if isinstance(node, ast.GeneratorExp):
            return KIND_UNKNOWN  # generator object, not a sequence
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return CONSTRUCTOR_KINDS.get(node.func.id, KIND_UNKNOWN)
        return KIND_UNKNOWN
