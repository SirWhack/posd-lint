"""Finding record — the single output unit shared by detectors and the judge."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class JudgeVerdict(str, Enum):
    REAL = "real"
    BORDERLINE = "borderline"
    FALSE_POSITIVE = "false_positive"
    UNJUDGED = "unjudged"


@dataclass
class Finding:
    """A single PoSD red flag candidate.

    Detectors emit Findings with deterministic content (file, line, evidence).
    The judge mutates judge_* fields after AI review; until then, judge_verdict
    is UNJUDGED. Reports render both layers when present.
    """

    file: str
    line: int
    detector: str           # stable id, e.g. "shallow_class"
    title: str              # one-line headline
    evidence: str           # specific measurement that triggered, e.g. "21 public methods"
    rubric_ref: str         # section reference into posd-reference.md, e.g. "5"
    rubric_title: str       # human title of that section
    severity: Severity = Severity.MEDIUM
    end_line: Optional[int] = None
    code_excerpt: str = ""  # filled by parse layer; the AI judge needs context

    judge_verdict: JudgeVerdict = JudgeVerdict.UNJUDGED
    judge_reasoning: str = ""
    judge_recommendation: str = ""

    def location(self) -> str:
        """Render a clickable file:line reference for terminals/editors."""
        if self.end_line and self.end_line != self.line:
            return f"{self.file}:{self.line}-{self.end_line}"
        return f"{self.file}:{self.line}"
