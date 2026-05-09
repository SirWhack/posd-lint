"""Claude-based judge.

Supports two transport modes:
- Direct Anthropic API (ANTHROPIC_API_KEY environment variable).
- Azure AI Foundry (AZURE_FOUNDRY_API_KEY + AZURE_FOUNDRY_ENDPOINT) — same shape
  the time-tracker codebase already uses, so this works against existing creds.

The judge mutates Findings in place: setting judge_verdict, judge_reasoning,
and judge_recommendation. Findings whose judge_verdict is FALSE_POSITIVE are
typically dropped at the report layer; that decision is the report's, not the
judge's.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from posd_lint.findings import Finding, JudgeVerdict
from posd_lint.judge.prompts import (
    build_system_prompt,
    build_user_prompt,
    index_sections,
    load_rubric,
    load_rubric_from_path,
)


logger = logging.getLogger(__name__)


@dataclass
class JudgeConfig:
    """Knobs for the judge — kept narrow on purpose.

    rubric_path: optional override for the bundled posd-reference.md. If unset,
        the package's copy is used.
    model: Claude model id. Defaults to a current Sonnet — fast, cheap, accurate
        enough for code-review judgment. Override for Opus on large reviews.
    max_tokens: cap on judge response. 800 is plenty for verdict + reasoning +
        recommendation; the JSON envelope is tight by design.
    """
    rubric_path: Optional[Path] = None
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 800


class ClaudeJudge:
    """Reviews deterministic findings with Claude using PoSD as the rubric."""

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self.config = config or JudgeConfig()
        rubric = (
            load_rubric_from_path(self.config.rubric_path)
            if self.config.rubric_path
            else load_rubric()
        )
        self.sections = index_sections(rubric)
        self._system_prompt = build_system_prompt(rubric)
        self._client = _build_client()

    def judge(self, finding: Finding) -> Finding:
        """Mutate finding with judge fields. Returns the same finding for chaining.

        On any failure (API error, malformed JSON, missing rubric section) the
        finding is returned with judge_verdict=UNJUDGED and the failure recorded
        in judge_reasoning. We never crash the run for a single bad finding.
        """
        if finding.rubric_ref not in self.sections:
            finding.judge_reasoning = f"No rubric section §{finding.rubric_ref} found."
            return finding

        user_prompt = build_user_prompt(
            detector_name=finding.detector,
            finding_title=finding.title,
            evidence=finding.evidence,
            file_path=finding.file,
            line=finding.line,
            rubric_section_number=finding.rubric_ref,
            code_excerpt=finding.code_excerpt or "(no excerpt)",
        )

        try:
            raw = self._call(user_prompt)
        except Exception as e:
            logger.warning("Judge call failed for %s: %s", finding.location(), e)
            finding.judge_reasoning = f"Judge call failed: {e}"
            return finding

        parsed = _parse_response(raw)
        if parsed is None:
            finding.judge_reasoning = f"Judge returned malformed JSON: {raw[:200]}"
            return finding

        verdict = parsed.get("verdict", "")
        try:
            finding.judge_verdict = JudgeVerdict(verdict)
        except ValueError:
            finding.judge_reasoning = f"Unknown verdict: {verdict!r}"
            return finding

        finding.judge_reasoning = parsed.get("reasoning", "")
        finding.judge_recommendation = parsed.get("recommendation", "")
        return finding

    def _call(self, user_prompt: str) -> str:
        """Send the request and return the raw text content."""
        msg = self._client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": self._system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        return msg.content[0].text


def _build_client():
    """Build an Anthropic-compatible client from whatever creds are available.

    Preference order: direct Anthropic key, then Azure AI Foundry. We import
    the SDK lazily so users without it installed can still run --ai-judge none.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic
        return Anthropic()

    foundry_key = os.getenv("AZURE_FOUNDRY_API_KEY")
    foundry_url = os.getenv("AZURE_FOUNDRY_ENDPOINT")
    if foundry_key and foundry_url:
        from anthropic import AnthropicFoundry  # type: ignore[attr-defined]
        return AnthropicFoundry(api_key=foundry_key, base_url=foundry_url)

    raise RuntimeError(
        "No Anthropic credentials found. Set ANTHROPIC_API_KEY, or "
        "AZURE_FOUNDRY_API_KEY + AZURE_FOUNDRY_ENDPOINT, or run with --ai-judge none."
    )


JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parse_response(raw: str) -> dict | None:
    """Tolerant JSON parse — Claude usually returns clean JSON but occasionally
    wraps it in fences or prefixes with prose. Strip and try again."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = JSON_OBJECT.search(raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None
