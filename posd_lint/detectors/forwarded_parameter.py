"""Function parameters that exist only to be forwarded (PoSD §8).

Ousterhout's pass-through variable: 'a piece of data threaded through several
layers that don't use it, just so a deep layer can reach it.' The middle
layers know about something irrelevant to their abstraction.

This detector handles the *intra-function* version: a parameter that's only
mentioned once in the body, as an argument to another call. Cross-function
threading needs full call-graph analysis (deferred to a later phase); the
intra-function case is detectable from the AST alone and surfaces the same
smell at the function level.

Detection shape:
- For each function with ≥3 params, count how many times each param is
  *read* in the body.
- A param read exactly once, where the single read is as a Call argument,
  is forwarded. Flag.

False-positive avoidance:
- Skip functions with `**kwargs` — it's common to accept-and-forward kwargs.
- Skip dunder methods.
- Skip params whose only use is in an isinstance/type check (legitimate use).
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


MIN_PARAMS = 3   # functions with 1-2 params are too small to bother flagging

# Forwarded params are a smell when the *function* is a wrapper — small body
# whose primary work is calling out. In a function with substantial logic,
# normalizing or routing a few params at the top isn't pass-through, it's
# preprocessing. We only flag wrappers.
MAX_WRAPPER_BODY_STMTS = 6


@register
class ForwardedParameterDetector(Detector):
    name = "forwarded_parameter"
    title = "Parameter is only forwarded, never used"
    rubric_ref = "8"
    rubric_title = "Different layer, different abstraction"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            if node.args.kwarg is not None:
                continue  # **kwargs forwarding — too noisy to flag

            params = self.function_param_names(node)
            if len(params) < MIN_PARAMS:
                continue
            if self._body_size(node) > MAX_WRAPPER_BODY_STMTS:
                continue

            for param in params:
                usage = self._classify_param_usage(node, param)
                if usage is None:
                    continue
                yield Finding(
                    file=file.path,
                    line=node.lineno,
                    detector=self.name,
                    title=f"Parameter '{param}' of '{node.name}' is only forwarded",
                    evidence=f"used exactly once, as an argument to {usage}",
                    rubric_ref=self.rubric_ref,
                    rubric_title=self.rubric_title,
                    severity=Severity.LOW,
                    code_excerpt=file.excerpt(node.lineno, node.lineno + 3, context=1),
                )

    def _classify_param_usage(
        self, fn: ast.FunctionDef | ast.AsyncFunctionDef, param: str
    ) -> str | None:
        """Return target-name if param is read exactly once and the read is a Call arg.

        Returns None if param is read 0 times, ≥2 times, or its single read
        isn't an argument to a call (e.g. it's used in a comparison, a return
        expression, etc.).
        """
        reads: list[ast.Name] = []
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Name) and sub.id == param and isinstance(sub.ctx, ast.Load):
                reads.append(sub)
        if len(reads) != 1:
            return None

        # The read must be a direct argument of a Call (positional or keyword value).
        read_node = reads[0]
        for sub in ast.walk(fn):
            if not isinstance(sub, ast.Call):
                continue
            if any(arg is read_node for arg in sub.args):
                return self._call_target(sub.func)
            if any(kw.value is read_node for kw in sub.keywords):
                return self._call_target(sub.func)
        return None

    @staticmethod
    def _call_target(func: ast.expr) -> str:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return f"...{func.attr}"
        return "<call>"

    @staticmethod
    def _body_size(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """Count statements in body, walked. Same metric as shallow_class /
        conjoined_methods uses — we want to recognize the same 'wrapper'
        shape across detectors."""
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        return sum(1 for stmt in body for sub in ast.walk(stmt) if isinstance(sub, ast.stmt))
