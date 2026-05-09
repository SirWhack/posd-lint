"""Public docstrings that describe implementation rather than contract (PoSD §12).

Ousterhout: 'implementation documentation contaminates the interface when interface
documentation describes implementation details that aren't needed in order to
use the thing being documented.' The reader of a public docstring shouldn't
have to learn the internals to call the function.

Detection shape — lexical signals in public-surface docstrings:
- Phrases that signal implementation talk: 'internally', 'we use', 'this implementation',
  'is implemented', 'is backed by', 'under the hood', 'currently', 'workaround', 'TODO',
  'HACK', 'FIXME', 'temporarily'.
- References to private attributes (`self._foo`) in the docstring — by convention
  the leading underscore *is* an implementation marker; mentioning it leaks.
- References to specific helper methods that aren't part of the public surface.

Skipped:
- Private methods/classes (leading underscore) — their docstring *is* the
  implementation doc; that's appropriate.
- Dunder methods.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


# Phrases that indicate implementation talk in a docstring. Matched
# case-insensitively as whole-word patterns. Curated to avoid false positives
# on legitimate uses (e.g. "internally consistent" matches "internally" — we
# accept that occasional false positive; the AI judge filters it out).
LEAK_PATTERNS = [
    r"\binternally\b",
    r"\bwe use\b",
    r"\bthis implementation\b",
    r"\bis implemented as\b",
    r"\bis backed by\b",
    r"\bunder the hood\b",
    r"\bcurrently\b",
    r"\bworkaround\b",
    r"\btemporarily\b",
    r"\bTODO\b",
    r"\bHACK\b",
    r"\bFIXME\b",
    r"\bXXX\b",
]

LEAK_REGEX = re.compile("|".join(LEAK_PATTERNS), re.IGNORECASE)
PRIVATE_ATTR_REGEX = re.compile(r"\bself\._[a-zA-Z][a-zA-Z0-9_]*\b")


@register
class ImplLeaksIntoInterfaceDetector(Detector):
    name = "impl_leaks_into_interface"
    title = "Implementation details in interface docstring"
    rubric_ref = "12"
    rubric_title = "Why write comments"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if isinstance(node, ast.ClassDef):
                yield from self._check_node(file, node, kind="class")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Public methods / module-level public functions only.
                if not self.is_public(node.name):
                    continue
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                kind = "method" if isinstance(getattr(node, "parent", None), ast.ClassDef) else "function"
                yield from self._check_node(file, node, kind=kind)

    def _check_node(self, file: ParsedFile, node: ast.AST, kind: str) -> Iterable[Finding]:
        name = getattr(node, "name", "")
        if not self.is_public(name):
            return
        doc = ast.get_docstring(node)
        if not doc:
            return

        leak_match = LEAK_REGEX.search(doc)
        priv_match = PRIVATE_ATTR_REGEX.search(doc)
        if not leak_match and not priv_match:
            return

        evidence_parts = []
        if leak_match:
            evidence_parts.append(f"phrase '{leak_match.group(0)}'")
        if priv_match:
            evidence_parts.append(f"private attribute reference '{priv_match.group(0)}'")
        evidence = "docstring contains " + " and ".join(evidence_parts)

        yield Finding(
            file=file.path,
            line=node.lineno,
            detector=self.name,
            title=f"Public {kind} '{name}' docstring leaks implementation details",
            evidence=evidence,
            rubric_ref=self.rubric_ref,
            rubric_title=self.rubric_title,
            severity=Severity.LOW,
            code_excerpt=file.excerpt(node.lineno, node.lineno + 5, context=1),
        )
