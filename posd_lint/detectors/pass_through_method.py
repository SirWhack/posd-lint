"""Methods whose body is a single forwarding call (PoSD §8).

Ousterhout's pass-through method: 'a method that does nothing except pass its
arguments to another method, usually with the same API.' The boundary between
the two classes is in the wrong place — either the wrapper isn't paying for
its interface, or the wrapped method should be public.

Detection shape:
- The method body is exactly one statement (excluding docstring).
- That statement is a Return, Expression, or Await of a Call.
- The call's positional/keyword args mirror the wrapper's params 1:1.

We deliberately allow wrappers that *transform* arguments (`return self.x.f(arg.upper())`)
or that *add* an argument the caller doesn't supply — those are doing real work.
What we flag is forwarding without adaptation, which is the textbook smell.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


@register
class PassThroughMethodDetector(Detector):
    name = "pass_through_method"
    title = "Pass-through method"
    rubric_ref = "8"
    rubric_title = "Different layer, different abstraction"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for cls in ast.walk(file.tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for item in cls.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                # Skip dunder methods — language semantics often require thin shims.
                if item.name.startswith("__") and item.name.endswith("__"):
                    continue
                target = self._is_pass_through(item)
                if target is None:
                    continue
                yield Finding(
                    file=file.path,
                    line=item.lineno,
                    detector=self.name,
                    title=f"Method '{cls.name}.{item.name}' just forwards to '{target}'",
                    evidence=f"single forwarding call to {target}; arguments unchanged",
                    rubric_ref=self.rubric_ref,
                    rubric_title=self.rubric_title,
                    severity=Severity.MEDIUM,
                    end_line=item.end_lineno,
                    code_excerpt=file.excerpt(item.lineno, item.end_lineno or item.lineno, context=1),
                )

    def _is_pass_through(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        """Return the call target name if this is a pass-through, else None."""
        body = node.body
        # Strip docstring.
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        if len(body) != 1:
            return None

        call = self._extract_call(body[0])
        if call is None:
            return None

        # Args must be a 1:1 forward of the wrapper's params.
        if not self._args_match(node, call):
            return None

        return self._call_target(call.func)

    @staticmethod
    def _extract_call(stmt: ast.stmt) -> ast.Call | None:
        """Pull a Call out of Return / Expr / Await wrappers."""
        if isinstance(stmt, ast.Return):
            value = stmt.value
        elif isinstance(stmt, ast.Expr):
            value = stmt.value
        else:
            return None
        if isinstance(value, ast.Await):
            value = value.value
        if isinstance(value, ast.Call):
            return value
        return None

    def _args_match(self, node: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call) -> bool:
        """The call's args mirror the wrapper's params, with no transformation.

        Positional args must be Names matching wrapper params in order. Keyword
        args may be skipped (wrappers often pass kwargs through implicitly via
        **kwargs which we don't try to track). Any literal, attribute access,
        or expression in the call args means the wrapper is doing real work
        and we don't flag it.
        """
        wrapper_params = self.function_param_names(node)
        if not wrapper_params and not call.args and not call.keywords:
            # No params, no args — trivial helper; might be pass-through but
            # usually too small to matter. Don't flag.
            return False

        # All positional args must be plain Names matching wrapper params, in order.
        for i, arg in enumerate(call.args):
            if isinstance(arg, ast.Starred):
                # *args forwarding is a pass-through pattern; accept.
                if isinstance(arg.value, ast.Name) and arg.value.id == "args":
                    continue
                return False
            if not isinstance(arg, ast.Name):
                return False
            if i >= len(wrapper_params) or arg.id != wrapper_params[i]:
                return False

        # Keyword args must be name=name forwarding (key matches name passed).
        for kw in call.keywords:
            if kw.arg is None:
                # **kwargs forwarding
                if isinstance(kw.value, ast.Name) and kw.value.id == "kwargs":
                    continue
                return False
            if not isinstance(kw.value, ast.Name):
                return False
            if kw.value.id not in wrapper_params:
                return False

        return True

    @staticmethod
    def _call_target(func: ast.expr) -> str:
        """Render the call target as a dotted string for the finding evidence."""
        if isinstance(func, ast.Attribute):
            return f"{PassThroughMethodDetector._call_target(func.value)}.{func.attr}"
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Call):
            return PassThroughMethodDetector._call_target(func.func) + "()"
        return "<expr>"
