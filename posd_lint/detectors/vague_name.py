"""Detect generic, image-free identifiers (PoSD §13).

Names like `data`, `result`, `manager` convey nothing the reader didn't already
know from context. They're a hint the abstraction is vague — though the AI judge
gets the final call on whether each instance is genuinely vague or just a
domain-appropriate short name.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable, Optional

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

# Versioning / replacement suffixes — "I made another one and didn't rename
# the original": process_v2, handler_new, parse_actually, foo_old, x_tmp.
# Matched on snake_case identifiers; trailing digits also picked up via _v\d+.
VERSIONED_SUFFIX_RE = re.compile(
    r"_(v\d+|new|old|actual|actually|final|real|fixed|tmp)$",
    re.IGNORECASE,
)

# CamelCase suffix variant: "User2", "RequestV2".
CAMEL_VERSIONED_SUFFIX_RE = re.compile(r"(V\d+|\d+)$")

# Word-as-prefix on otherwise-generic stems: real_data, final_result,
# actual_user, new_thing. Same "differentiating without saying how" smell.
VERSIONED_PREFIX_RE = re.compile(
    r"^(real|final|actual|new|old|tmp|fixed)_",
    re.IGNORECASE,
)

# "Adjective-only" suffixes Ousterhout calls out: foo_helper, render_utility.
# Their information content is zero — the suffix says "this exists" and nothing
# more. Restricted to functions; classes named `*Helper` are too entrenched.
ADJECTIVE_SUFFIX_RE = re.compile(r"_(helper|utility|utilities|helpers)$", re.IGNORECASE)


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
            yield self._make_finding(
                file, name, line, kind,
                title=f"Vague {kind} name: {name!r}",
                reason=f"generic name '{name}'",
            )
            return
        # Numbered-suffix on a generic stem: data1, data2, result_v2 …
        if any(lower.startswith(g) and len(lower) > len(g) and lower[len(g)] in NUMBERED_SUFFIX_HINT
               for g in self.generic_names):
            yield self._make_finding(
                file, name, line, kind,
                title=f"Vague {kind} name: {name!r}",
                reason=f"numbered generic name '{name}'",
            )
            return
        # Versioned identifier: process_v2, handler_new, User2, RequestV3 …
        # Says "this is a different one" without saying *how* it differs.
        versioned_marker = self._versioned_marker(name)
        if versioned_marker is not None:
            yield self._make_finding(
                file, name, line, kind,
                title=f"Versioned identifier: {name!r}",
                reason=f"versioned suffix '{versioned_marker}' — encodes 'another one' without saying how it differs",
            )
            return
        # Word-as-prefix counterpart: real_data, final_result, actual_user.
        prefix_match = VERSIONED_PREFIX_RE.match(name)
        if prefix_match:
            yield self._make_finding(
                file, name, line, kind,
                title=f"Differentiating-without-content prefix: {name!r}",
                reason=f"prefix '{prefix_match.group(1).lower()}_' implies a contrast that the name doesn't describe",
            )
            return
        # Adjective-only suffix on a function: foo_helper, render_utility.
        if kind == "function" and ADJECTIVE_SUFFIX_RE.search(name):
            yield self._make_finding(
                file, name, line, kind,
                title=f"Differentiating-without-content suffix: {name!r}",
                reason="suffix 'helper'/'utility' adds no information about what the function does",
            )
            return
        # Single-letter names outside obvious loop counters at top of file scope.
        if len(name) == 1 and name not in ("i", "j", "k", "x", "y", "z", "_") and kind != "parameter":
            yield self._make_finding(
                file, name, line, kind,
                title=f"Vague {kind} name: {name!r}",
                reason=f"single-letter name '{name}'",
            )

    def _versioned_marker(self, name: str) -> Optional[str]:
        """Return the matched suffix if `name` looks versioned, else None.

        Snake_case suffixes (`_v2`, `_new`, `_actually`) match anywhere a
        snake suffix is plausible. CamelCase suffixes (`User2`, `RequestV3`)
        match only when the stem is meaningfully present — we don't want to
        flag genuine domain names that happen to end in a digit (e.g. `Sha256`
        is not "Sha2 v56"). The heuristic: the stem must contain a lowercase
        letter, ruling out short uppercase acronyms.
        """
        m = VERSIONED_SUFFIX_RE.search(name)
        if m:
            return m.group(0)
        m2 = CAMEL_VERSIONED_SUFFIX_RE.search(name)
        if m2:
            stem = name[: m2.start()]
            if stem and stem[0].isupper() and any(c.islower() for c in stem):
                return m2.group(0)
        return None

    def _make_finding(
        self,
        file: ParsedFile,
        name: str,
        line: int,
        kind: str,
        *,
        title: str,
        reason: str,
    ) -> Finding:
        return Finding(
            file=file.path,
            line=line,
            detector=self.name,
            title=title,
            evidence=reason,
            rubric_ref=self.rubric_ref,
            rubric_title=self.rubric_title,
            severity=Severity.LOW,
            code_excerpt=file.excerpt(line, line, context=2),
        )
