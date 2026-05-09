"""Validate that `posd-lint --format json` output conforms to the published schema."""

from __future__ import annotations

import json
from pathlib import Path

from posd_lint.findings import Finding, JudgeVerdict, Severity
from posd_lint.report import render_json


SCHEMA_PATH = Path(__file__).parent.parent / "posd_lint" / "data" / "findings.schema.json"


def _sample_findings() -> list[Finding]:
    return [
        Finding(
            file="foo/bar.py",
            line=10,
            detector="shallow_class",
            title="Class Foo: 21 public methods",
            evidence="21 public methods",
            rubric_ref="5",
            rubric_title="Deep vs. shallow modules",
            severity=Severity.HIGH,
            end_line=42,
            code_excerpt="class Foo:\n    pass",
        ),
        Finding(
            file="foo/baz.py",
            line=3,
            detector="vague_name",
            title="Generic identifier 'data'",
            evidence="name='data'",
            rubric_ref="13",
            rubric_title="Naming",
            severity=Severity.LOW,
            end_line=None,
            code_excerpt="data = []",
            judge_verdict=JudgeVerdict.REAL,
            judge_reasoning="The name does not describe the contents.",
            judge_recommendation="Rename to `pending_jobs`.",
        ),
    ]


def test_schema_file_is_valid_json():
    schema = json.loads(SCHEMA_PATH.read_text())
    assert schema["type"] == "array"
    assert "Finding" in schema["definitions"]


def test_render_json_matches_schema():
    findings = _sample_findings()
    payload = json.loads(render_json(findings))

    try:
        import jsonschema
    except ImportError:
        _manual_validate(payload)
        return

    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(payload, schema)


def test_real_cli_output_matches_schema(tmp_path):
    import subprocess
    import sys

    target = Path(__file__).parent.parent / "posd_lint" / "detectors" / "duplicate_code.py"
    out = tmp_path / "out.json"
    subprocess.run(
        [
            sys.executable, "-m", "posd_lint.cli",
            str(target), "--ai-judge", "none",
            "--format", "json", "--output", str(out),
        ],
        check=True,
        cwd=Path(__file__).parent.parent,
    )

    payload = json.loads(out.read_text())
    assert isinstance(payload, list) and len(payload) > 0

    try:
        import jsonschema
    except ImportError:
        _manual_validate(payload)
        return

    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(payload, schema)


def _manual_validate(payload):
    assert isinstance(payload, list)
    required = {
        "file", "line", "detector", "title", "evidence",
        "rubric_ref", "rubric_title", "severity", "judge_verdict",
    }
    severities = {"info", "low", "medium", "high"}
    verdicts = {"unjudged", "real", "borderline", "false_positive"}
    for item in payload:
        assert isinstance(item, dict)
        assert required.issubset(item.keys()), f"missing keys: {required - item.keys()}"
        assert isinstance(item["line"], int) and item["line"] >= 1
        assert item["severity"] in severities
        assert item["judge_verdict"] in verdicts
        assert item["end_line"] is None or isinstance(item["end_line"], int)
