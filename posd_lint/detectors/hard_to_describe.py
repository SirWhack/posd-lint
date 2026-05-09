"""Missing or trivial docstrings on public surfaces (PoSD §12, §14).

Ousterhout's claim: if you can't write a clean comment for it, the abstraction
is wrong. This detector flags the cheapest version — public methods, classes,
and module-level functions with no docstring or a one-line stub. The judge
decides whether each is genuine missing-contract or fine-as-is.

Private helpers (leading underscore) are out of scope here; their contracts
are local. Dunder methods are out of scope too — their contract is the
language's, not yours.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


SHORT_BODY_LINES = 3   # very short functions don't need docstrings; trivial property accessors etc.
MIN_DOCSTRING_CHARS = 15  # under this, the docstring is a stub like '"""Save."""'


@register
class HardToDescribeDetector(Detector):
    name = "hard_to_describe"
    title = "Public surface lacks a clear docstring"
    rubric_ref = "12"
    rubric_title = "Why write comments"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for node in ast.walk(file.tree):
            if isinstance(node, ast.ClassDef):
                yield from self._check_class(file, node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Module-level public functions only — methods are handled
                # via their enclosing class so we skip them here.
                if isinstance(getattr(node, "parent", None), ast.Module):
                    yield from self._check_function(file, node, kind="function")

    def _check_class(self, file: ParsedFile, node: ast.ClassDef) -> Iterable[Finding]:
        if not self.is_public(node.name):
            return
        if not self._has_real_docstring(node):
            yield self._make(file, node.name, node.lineno, kind="class",
                             evidence="no docstring or stub-only docstring")
        # Public methods on this class.
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self.is_public(item.name) and not item.name.startswith("__"):
                    yield from self._check_function(file, item, kind="method")

    def _check_function(self, file: ParsedFile, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> Iterable[Finding]:
        if not self.is_public(node.name):
            return
        if self._body_lines(node) <= SHORT_BODY_LINES:
            return  # trivial getter/setter equivalent — docstring would be noise
        if self._has_real_docstring(node):
            return
        yield self._make(file, node.name, node.lineno, kind=kind,
                         evidence="no docstring or stub-only docstring")

    @staticmethod
    def _has_real_docstring(node: ast.AST) -> bool:
        doc = ast.get_docstring(node)
        return bool(doc) and len(doc.strip()) >= MIN_DOCSTRING_CHARS

    @staticmethod
    def _body_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """Approximate body line count — for skipping trivial functions."""
        if not node.body:
            return 0
        return (node.body[-1].end_lineno or node.body[-1].lineno) - node.body[0].lineno + 1

    def _make(self, file: ParsedFile, name: str, line: int, kind: str, evidence: str) -> Finding:
        return Finding(
            file=file.path,
            line=line,
            detector=self.name,
            title=f"Public {kind} '{name}' lacks a clear docstring",
            evidence=evidence,
            rubric_ref=self.rubric_ref,
            rubric_title=self.rubric_title,
            severity=Severity.LOW,
            code_excerpt=file.excerpt(line, line, context=3),
        )
