"""Prompt construction and rubric-section extraction for the AI judge.

The full PoSD rubric is loaded once at import time and embedded in the
system prompt. Anthropic prompt caching makes this ~free after the first
call: the rubric is the cached prefix, and per-finding user prompts just
reference the relevant section by number.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path


SECTION_HEADER = re.compile(r"^##\s+(\d+)\.\s+(.+?)(?:\s+\(.+?\))?\s*$", re.MULTILINE)


def load_rubric() -> str:
    """Return the bundled posd-reference.md as a string."""
    pkg = resources.files("posd_lint.data")
    return (pkg / "posd-reference.md").read_text(encoding="utf-8")


def load_rubric_from_path(path: Path) -> str:
    """Override the bundled rubric with a user-supplied file."""
    return path.read_text(encoding="utf-8")


def index_sections(rubric: str) -> dict[str, str]:
    """Map section number -> section body text.

    Sections are matched by '## N. Title' headers. The body for section N
    runs from that header up to the next '## ' header (or end of file).
    Subsections like '## Part I —' are skipped because they have no number.
    """
    matches = list(SECTION_HEADER.finditer(rubric))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        num = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(rubric)
        out[num] = rubric[start:end].rstrip()
    return out


_PERSONA = """\
You are a code reviewer applying John Ousterhout's "A Philosophy of Software Design" principles.

A deterministic detector has flagged something in real code. Your job is to:
1. Decide whether the finding is genuinely a problem ("real"), arguable ("borderline"), or noise ("false_positive").
2. Write a short, concrete recommendation grounded in the cited rubric section.

Decision rules:
- Use ONLY the rubric section cited in the user prompt. Do not invoke principles from outside that section.
- Real: the rubric clearly applies and the code violates it.
- Borderline: the rubric applies but the code has reasonable justification, or the violation is mild.
- False positive: the detector's heuristic misfired; this is fine code or not what the rubric is about.

The complete PoSD rubric follows. Each top-level numbered section ('## N. Title') is the unit you will be asked to apply."""


_SCHEMA = """\
Output strict JSON only — no markdown fences, no commentary outside the JSON:
{
  "verdict": "real" | "borderline" | "false_positive",
  "reasoning": "One sentence. Cite the rubric.",
  "recommendation": "2-4 sentences. Reference specific identifiers from the code excerpt. If false_positive, leave empty string."
}"""


def build_system_prompt(rubric: str) -> str:
    """Assemble the full system prompt: persona + rubric + output schema."""
    return f"{_PERSONA}\n\n{rubric}\n\n{_SCHEMA}"


SYSTEM_PROMPT = build_system_prompt(load_rubric())


def build_user_prompt(
    *,
    detector_name: str,
    finding_title: str,
    evidence: str,
    file_path: str,
    line: int,
    rubric_section_number: str,
    code_excerpt: str,
) -> str:
    """Assemble the per-finding user message for the judge.

    The rubric section itself lives in the cached system prompt; here we
    only reference it by number so the model knows which one to apply.
    """
    return f"""\
Apply §{rubric_section_number} to the following finding.

CODE EXCERPT ({file_path}:{line}):
```python
{code_excerpt}
```

---

DETECTOR: {detector_name}
TITLE: {finding_title}
EVIDENCE: {evidence}

Verdict?
"""
