"""Methods entangled with each other (PoSD §10).

Ousterhout: 'if you can't understand one method without also understanding
another method's implementation' the two were one method that got cut in half.

Detection shape (intra-class call graph, conservative):
- A calls B (via self.B(...) inside a class).
- B is private (leading underscore) — public-to-public coupling is harder to
  judge without semantic analysis, so we leave it for the AI judge to flag
  via wide-interface or pass-through detectors.
- B is *only* called by A within the class. (If B is called by multiple
  methods, it's a shared helper and probably fine.)
- B has non-trivial body — a 1-line helper isn't really "conjoined," it's
  inlined-but-named.

The output names both methods so the judge can read both bodies and decide
whether they should be a single method or are legitimately decomposed.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


# A "trivial" helper has fewer body statements than this — we don't flag those
# as conjoined, since extracting them was a naming choice, not a decomposition.
TRIVIAL_BODY_THRESHOLD = 3

# If one method has at least this many private-and-only-once-called callees,
# it's almost certainly a dispatcher (switch-table over handlers). Calling
# every (dispatcher, handler) pair conjoined drowns the signal in noise —
# skip pairs from such dispatchers.
DISPATCHER_FANOUT_THRESHOLD = 5


@register
class ConjoinedMethodsDetector(Detector):
    name = "conjoined_methods"
    title = "Conjoined methods"
    rubric_ref = "10"
    rubric_title = "Better together or better apart"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for cls in ast.walk(file.tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            yield from self._detect_in_class(file, cls)

    def _detect_in_class(self, file: ParsedFile, cls: ast.ClassDef) -> Iterable[Finding]:
        methods = {
            item.name: item
            for item in cls.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if len(methods) < 2:
            return

        # Build callers map: method_name -> set of methods that call it via self.
        # We only count calls of the form self.<name>(...) — not self.attr.x(...),
        # which references collaborators, not other methods on this class.
        callers: dict[str, set[str]] = defaultdict(set)
        for caller_name, caller_node in methods.items():
            for node in ast.walk(caller_node):
                if not isinstance(node, ast.Call):
                    continue
                callee = self._self_method_name(node.func)
                if callee and callee in methods and callee != caller_name:
                    callers[callee].add(caller_name)

        # Identify dispatchers — methods whose own callees are mostly single-use
        # private helpers. These are switch-tables, not entanglement; pairs
        # from a dispatcher caller are excluded.
        single_use_callees_by_caller: dict[str, int] = defaultdict(int)
        for callee_name, caller_set in callers.items():
            if len(caller_set) == 1 and callee_name.startswith("_"):
                single_use_callees_by_caller[next(iter(caller_set))] += 1
        dispatchers = {
            caller for caller, count in single_use_callees_by_caller.items()
            if count >= DISPATCHER_FANOUT_THRESHOLD
        }

        # Flag private callees with exactly one caller and a non-trivial body.
        for callee_name, caller_set in callers.items():
            if len(caller_set) != 1:
                continue
            if not callee_name.startswith("_"):
                continue
            if callee_name.startswith("__") and callee_name.endswith("__"):
                continue
            callee_node = methods[callee_name]
            if self._body_size(callee_node) < TRIVIAL_BODY_THRESHOLD:
                continue
            caller_name = next(iter(caller_set))
            if caller_name in dispatchers:
                continue
            caller_node = methods[caller_name]
            yield Finding(
                file=file.path,
                line=callee_node.lineno,
                detector=self.name,
                title=f"'{cls.name}.{caller_name}' and '{cls.name}.{callee_name}' are conjoined",
                evidence=(
                    f"'{callee_name}' is only called by '{caller_name}'; "
                    f"reading one requires reading the other"
                ),
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.LOW,
                end_line=callee_node.end_lineno,
                code_excerpt=self._render_pair(file, caller_node, callee_node),
            )

    @staticmethod
    def _self_method_name(func: ast.expr) -> str | None:
        """Return the method name if func is `self.<name>`, else None.

        We look only at one-level `self.X` — multi-level `self.collab.X` is
        a reference to another object's API, not entanglement within the class.
        """
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "self":
            return func.attr
        return None

    @staticmethod
    def _body_size(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """Count statements in body, walked. Same metric as shallow_class."""
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        return sum(1 for stmt in body for _ in ast.walk(stmt) if isinstance(_, ast.stmt))

    @staticmethod
    def _render_pair(file: ParsedFile, caller: ast.AST, callee: ast.AST) -> str:
        """Show both methods' headers so the judge can see the entanglement."""
        caller_lines = file.excerpt(caller.lineno, caller.lineno + 2, context=0)
        callee_lines = file.excerpt(callee.lineno, callee.lineno + 2, context=0)
        return f"{caller_lines}\n  ...\n{callee_lines}"
