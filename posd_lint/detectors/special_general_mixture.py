"""General-purpose functions with caller-specific type branches (PoSD §10).

Ousterhout's special-general mixture: a general mechanism that contains code
specialised for one particular caller. The smell shows up as `isinstance` /
`hasattr` chains in functions that name themselves generically — the function
*claims* to be general but is doing per-type dispatch internally.

Detection shape:
- Function has at least 2 isinstance(...) checks in its body, OR a single
  isinstance() followed by elif isinstance() chain.
- Function name does NOT itself signal that dispatch is the contract:
  dispatch_*, handle_*, route_*, parse_*, serialize_*, deserialize_*, render_*,
  visit_* — these are explicitly type-driven and the rubric doesn't apply.

False-positive avoidance:
- Custom __eq__ / __hash__ / __lt__ etc. need isinstance() for correctness; skip dunders.
- functools.singledispatch decorators are the right way to do dispatch — skip.
- isinstance() for runtime type-narrowing of Optional[T] or Union types is
  legitimate (`if isinstance(x, str): use x as str`); the threshold of ≥2
  filters most of these.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


# Function name prefixes / exact names where dispatch-by-type is the contract.
DISPATCH_NAME_PREFIXES = (
    "dispatch", "handle", "route", "parse", "serialize", "deserialize",
    "render", "visit", "format", "encode", "decode", "to_", "from_",
    "convert", "transform_", "as_", "_dispatch", "_handle",
)

ISINSTANCE_THRESHOLD = 2


@register
class SpecialGeneralMixtureDetector(Detector):
    name = "special_general_mixture"
    title = "Special-purpose code in a general-purpose function"
    rubric_ref = "10"
    rubric_title = "Better together or better apart"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if self._is_dispatch_named(node.name):
                continue
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            if self._has_singledispatch(node):
                continue
            count = self._count_isinstance_calls(node)
            if count < ISINSTANCE_THRESHOLD:
                continue
            yield Finding(
                file=file.path,
                line=node.lineno,
                detector=self.name,
                title=f"Function '{node.name}' branches on {count} isinstance() checks",
                evidence=(
                    f"{count} isinstance() calls inside a function whose name doesn't signal dispatch; "
                    f"likely a general-purpose mechanism with caller-specific branches"
                ),
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.LOW,
                end_line=node.end_lineno,
                code_excerpt=file.excerpt(node.lineno, min((node.end_lineno or node.lineno), node.lineno + 10), context=1),
            )

    @staticmethod
    def _is_dispatch_named(name: str) -> bool:
        lower = name.lower()
        return any(lower.startswith(prefix) for prefix in DISPATCH_NAME_PREFIXES)

    @staticmethod
    def _has_singledispatch(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for dec in node.decorator_list:
            name = dec.attr if isinstance(dec, ast.Attribute) else (dec.id if isinstance(dec, ast.Name) else "")
            if name in ("singledispatch", "singledispatchmethod"):
                return True
        return False

    @staticmethod
    def _count_isinstance_calls(node: ast.AST) -> int:
        count = 0
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "isinstance":
                count += 1
        return count
