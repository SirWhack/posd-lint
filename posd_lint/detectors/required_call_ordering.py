"""Classes with paired methods that imply unenforced call order (PoSD §6, §11).

Ousterhout's required-call-ordering smell: 'open() before read() before close()
with no enforcement.' The class invariant — what state it must be in for each
method to work — exists only in the author's head and the documentation.
Python has a clean answer: the context-manager protocol (__enter__/__exit__).
A class with paired methods that doesn't implement that protocol is leaving
the ordering invariant for callers to remember.

Detection shape:
- Class has a method whose name matches a 'begin' marker (start, open, init,
  begin, connect, acquire) AND a method whose name matches an 'end' marker
  (stop, close, shutdown, finish, end, disconnect, release).
- Class does NOT define both __enter__ and __exit__.
- Skip dataclasses and Enums (they don't have lifecycle).
- Skip if the begin method is __init__ — that's just a constructor.

False-positive avoidance:
- start_X / stop_X for an arbitrary X (e.g. start_timer / stop_timer) only
  flags if the X parts match — start_timer + stop_timer flags; start + close
  flags too (different X but classic pair); start_session + close_window
  doesn't (different X).
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


# Pairs of begin/end markers. Order matters in the output but the detector
# matches in any order. The structure is (begin_prefix, end_prefix).
PAIRS = [
    ("start", "stop"),
    ("start", "close"),
    ("open", "close"),
    ("begin", "end"),
    ("begin", "finish"),
    ("connect", "disconnect"),
    ("acquire", "release"),
    ("init", "shutdown"),
    ("setup", "teardown"),
    ("login", "logout"),
]


@register
class RequiredCallOrderingDetector(Detector):
    name = "required_call_ordering"
    title = "Lifecycle methods without context-manager protocol"
    rubric_ref = "6"
    rubric_title = "Information hiding vs. information leakage"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        for cls in ast.walk(file.tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if self._is_exempt(cls):
                continue
            method_names = {
                item.name for item in cls.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if "__enter__" in method_names and "__exit__" in method_names:
                continue  # context-managed; protocol enforces ordering
            pair = self._find_pair(method_names)
            if pair is None:
                continue
            begin_method, end_method = pair
            yield Finding(
                file=file.path,
                line=cls.lineno,
                detector=self.name,
                title=f"Class '{cls.name}' has '{begin_method}'/'{end_method}' but no __enter__/__exit__",
                evidence=(
                    f"paired lifecycle methods imply ordering, but no context-manager "
                    f"protocol enforces it"
                ),
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.LOW,
                end_line=cls.end_lineno,
                code_excerpt=file.excerpt(cls.lineno, cls.lineno + 2, context=1),
            )

    @staticmethod
    def _is_exempt(cls: ast.ClassDef) -> bool:
        for dec in cls.decorator_list:
            name = (
                dec.attr if isinstance(dec, ast.Attribute)
                else dec.id if isinstance(dec, ast.Name)
                else ""
            )
            if name in ("dataclass", "frozen_dataclass", "attrs", "define"):
                return True
        for base in cls.bases:
            name = (
                base.attr if isinstance(base, ast.Attribute)
                else base.id if isinstance(base, ast.Name)
                else ""
            )
            if name in ("Enum", "IntEnum", "StrEnum", "TypedDict", "NamedTuple", "Protocol"):
                return True
        return False

    def _find_pair(self, methods: set[str]) -> tuple[str, str] | None:
        """Look for a begin/end pair where the suffix (if any) matches.

        For exact prefixes (e.g. 'start' and 'stop' both as method names),
        returns ('start', 'stop'). For suffixed pairs ('start_timer' and
        'stop_timer'), the suffix must be the same on both sides.
        """
        for begin, end in PAIRS:
            for m in methods:
                if not m.startswith(begin):
                    continue
                # Skip __init__-style begins.
                if m == begin and begin == "init":
                    continue
                suffix = m[len(begin):]
                # No suffix: look for a bare end-name.
                if suffix == "":
                    if end in methods:
                        return m, end
                    continue
                # Suffix must start with _ (e.g. start_timer) — otherwise
                # 'started' would match 'start'.
                if not suffix.startswith("_"):
                    continue
                end_with_suffix = end + suffix
                if end_with_suffix in methods:
                    return m, end_with_suffix
        return None
