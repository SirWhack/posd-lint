"""Render findings as markdown or JSON.

Markdown grouping: by detector, then by file. Each finding shows location,
evidence, code excerpt, and the AI judge's verdict + recommendation when
present. False positives are dropped from the markdown report by default
(they're noise) but kept in the JSON output (the user might want to audit
them).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from typing import Iterable

from posd_lint.findings import Finding, JudgeVerdict, Severity


VERDICT_BADGE = {
    JudgeVerdict.REAL: "🟥 real",
    JudgeVerdict.BORDERLINE: "🟨 borderline",
    JudgeVerdict.FALSE_POSITIVE: "⬜ false positive",
    JudgeVerdict.UNJUDGED: "⬛ unjudged",
}


def render_markdown(findings: list[Finding], *, include_false_positives: bool = False) -> str:
    """Group findings by detector, render as markdown with code blocks.

    The header section gives a count summary so a reviewer can size up the
    report before reading. Findings are sorted within a detector by severity,
    then file path, then line.
    """
    findings = [
        f for f in findings
        if include_false_positives or f.judge_verdict != JudgeVerdict.FALSE_POSITIVE
    ]
    findings.sort(key=lambda f: (f.detector, _severity_rank(f.severity), f.file, f.line))

    by_detector: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_detector[f.detector].append(f)

    out: list[str] = []
    out.append("# PoSD Lint Report")
    out.append("")
    out.append(_summary_table(findings, by_detector))
    out.append("")

    for detector_name in sorted(by_detector):
        detector_findings = by_detector[detector_name]
        sample = detector_findings[0]
        out.append(f"## {detector_name} — {sample.title.split(':')[0] if ':' in sample.title else sample.rubric_title}")
        out.append("")
        out.append(f"_Rubric: §{sample.rubric_ref} {sample.rubric_title}_")
        out.append("")
        for f in detector_findings:
            out.append(_render_finding(f))
            out.append("")

    return "\n".join(out)


def render_json(findings: list[Finding]) -> str:
    """Full findings as JSON, including false positives. Useful for tooling."""
    payload = [_finding_to_json(f) for f in findings]
    return json.dumps(payload, indent=2)


def _summary_table(findings: list[Finding], by_detector: dict[str, list[Finding]]) -> str:
    """Render the header table with per-detector counts and verdicts."""
    if not findings:
        return "_No findings._"

    lines = ["| Detector | Total | Real | Borderline | Unjudged |",
             "|---|---|---|---|---|"]
    for name in sorted(by_detector):
        items = by_detector[name]
        verdicts = [i.judge_verdict for i in items]
        lines.append(
            f"| `{name}` | {len(items)} | "
            f"{verdicts.count(JudgeVerdict.REAL)} | "
            f"{verdicts.count(JudgeVerdict.BORDERLINE)} | "
            f"{verdicts.count(JudgeVerdict.UNJUDGED)} |"
        )
    return "\n".join(lines)


def _render_finding(f: Finding) -> str:
    """Render one finding as a markdown subsection."""
    verdict = VERDICT_BADGE[f.judge_verdict]
    lines = [
        f"### `{f.location()}` — {f.title}",
        "",
        f"- **Verdict:** {verdict}",
        f"- **Evidence:** {f.evidence}",
    ]
    if f.judge_reasoning:
        lines.append(f"- **Judge:** {f.judge_reasoning}")
    if f.code_excerpt:
        lines += ["", "```", f.code_excerpt, "```"]
    if f.judge_recommendation:
        lines += ["", "**Recommendation:**", "", f.judge_recommendation]
    return "\n".join(lines)


def _severity_rank(s: Severity) -> int:
    """Higher severity sorts first."""
    return {"high": 0, "medium": 1, "low": 2, "info": 3}[s.value]


def _finding_to_json(f: Finding) -> dict:
    """Asdict + enum coercion. asdict on dataclasses with Enum fields stores
    the enum as-is; we want the .value for JSON."""
    d = asdict(f)
    d["severity"] = f.severity.value
    d["judge_verdict"] = f.judge_verdict.value
    return d
