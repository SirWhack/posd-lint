"""Detect generic, image-free identifiers (PoSD §13).

Names like `data`, `result`, `manager` convey nothing the reader didn't already
know from context. They're a hint the abstraction is vague — though the AI judge
gets the final call on whether each instance is genuinely vague or just a
domain-appropriate short name.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


# Words that are red flags as identifier names. Tight loop counters (i, j, k)
# are excluded — they're scope-appropriate. So are domain words that happen
# to be generic in English but specific in code (e.g. "value" in a key/value
# data structure where it's the literal value).
GENERIC_NAMES = frozenset({
    "data", "info", "result", "manager", "handler", "util", "utils",
    "obj", "object", "item", "thing", "stuff", "tmp", "temp", "helper",
    "foo", "bar", "baz", "qux", "value_obj", "the_data", "my_data",
})

# Names that show "I couldn't think of one, so I numbered it." Strong signal.
NUMBERED_SUFFIX_HINT = "1234567890"


@register
class VagueNameDetector(Detector):
    name = "vague_name"
    title = "Vague or generic name"
    rubric_ref = "13"
    rubric_title = "Choosing names"

    def __init__(self, generic_names: frozenset[str] = GENERIC_NAMES):
        self.generic_names = generic_names

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from self._check(file, node.name, node.lineno, kind="function")
                # Param names too, except self/cls/loop-style short names.
                for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                    if arg.arg in ("self", "cls"):
                        continue
                    yield from self._check(file, arg.arg, arg.lineno, kind="parameter")
            elif isinstance(node, ast.ClassDef):
                yield from self._check(file, node.name, node.lineno, kind="class")
            elif isinstance(node, ast.Assign):
                # Only top-level assignments and class-body assignments —
                # local variables in function bodies are too noisy and many
                # are scope-appropriate (e.g. `result = compute()` is fine
                # if the function is named for what it returns).
                parent = getattr(node, "parent", None)
                if isinstance(parent, (ast.Module, ast.ClassDef)):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            yield from self._check(file, target.id, target.lineno, kind="variable")

    def _check(self, file: ParsedFile, name: str, line: int, kind: str) -> Iterable[Finding]:
        lower = name.lower()
        if lower in self.generic_names:
            yield self._make_finding(file, name, line, kind, reason=f"generic name '{name}'")
            return
        # Numbered-suffix on a generic stem: data1, data2, result_v2 …
        if any(lower.startswith(g) and len(lower) > len(g) and lower[len(g)] in NUMBERED_SUFFIX_HINT
               for g in self.generic_names):
            yield self._make_finding(file, name, line, kind, reason=f"numbered generic name '{name}'")
            return
        # Single-letter names outside obvious loop counters at top of file scope.
        if len(name) == 1 and name not in ("i", "j", "k", "x", "y", "z", "_") and kind != "parameter":
            yield self._make_finding(file, name, line, kind, reason=f"single-letter name '{name}'")

    def _make_finding(self, file: ParsedFile, name: str, line: int, kind: str, reason: str) -> Finding:
        return Finding(
            file=file.path,
            line=line,
            detector=self.name,
            title=f"Vague {kind} name: {name!r}",
            evidence=reason,
            rubric_ref=self.rubric_ref,
            rubric_title=self.rubric_title,
            severity=Severity.LOW,
            code_excerpt=file.excerpt(line, line, context=2),
        )
