"""Tests for inline + baseline suppression of findings."""

from __future__ import annotations

from pathlib import Path

from posd_lint.findings import Finding, Severity
from posd_lint.parse import parse_file
from posd_lint.suppress import (
    evidence_hash,
    is_suppressed,
    load_baseline,
    parse_inline_suppressions,
    write_baseline,
)


def _make_file(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _finding(file: str, line: int, detector: str, evidence: str = "evi") -> Finding:
    return Finding(
        file=file, line=line, detector=detector, title="t",
        evidence=evidence, rubric_ref="5", rubric_title="rt",
        severity=Severity.LOW,
    )


def test_inline_ignore_with_detector_name(tmp_path: Path):
    src = "x = 1  # posd-lint: ignore[vague_name]\n"
    f = _make_file(tmp_path, "a.py", src)
    parsed = parse_file(f)
    assert parsed is not None
    inline, file_level = parse_inline_suppressions([parsed])
    finding = _finding(str(f), 1, "vague_name")
    assert is_suppressed(finding, inline, file_level, set(), tmp_path) is True


def test_inline_ignore_with_detector_does_not_silence_others(tmp_path: Path):
    src = "x = 1  # posd-lint: ignore[vague_name]\n"
    f = _make_file(tmp_path, "a.py", src)
    parsed = parse_file(f)
    assert parsed is not None
    inline, file_level = parse_inline_suppressions([parsed])
    other = _finding(str(f), 1, "duplicate_code")
    assert is_suppressed(other, inline, file_level, set(), tmp_path) is False


def test_inline_ignore_bare_silences_any_detector(tmp_path: Path):
    src = "x = 1  # posd-lint: ignore\n"
    f = _make_file(tmp_path, "a.py", src)
    parsed = parse_file(f)
    assert parsed is not None
    inline, file_level = parse_inline_suppressions([parsed])
    for det in ("vague_name", "shallow_class", "anything"):
        finding = _finding(str(f), 1, det)
        assert is_suppressed(finding, inline, file_level, set(), tmp_path) is True


def test_inline_ignore_multiple_detectors(tmp_path: Path):
    src = "x = 1  # posd-lint: ignore[vague_name, shallow_class]\n"
    f = _make_file(tmp_path, "a.py", src)
    parsed = parse_file(f)
    assert parsed is not None
    inline, file_level = parse_inline_suppressions([parsed])
    assert is_suppressed(_finding(str(f), 1, "vague_name"), inline, file_level, set(), tmp_path)
    assert is_suppressed(_finding(str(f), 1, "shallow_class"), inline, file_level, set(), tmp_path)
    assert not is_suppressed(_finding(str(f), 1, "duplicate_code"), inline, file_level, set(), tmp_path)


def test_ignore_file_silences_entire_file(tmp_path: Path):
    src = "# posd-lint: ignore-file\nx = 1\ny = 2\n"
    f = _make_file(tmp_path, "a.py", src)
    parsed = parse_file(f)
    assert parsed is not None
    inline, file_level = parse_inline_suppressions([parsed])
    for line in (1, 2, 3, 99):
        for det in ("vague_name", "shallow_class"):
            finding = _finding(str(f), line, det)
            assert is_suppressed(finding, inline, file_level, set(), tmp_path) is True


def test_baseline_tuple_suppresses_match(tmp_path: Path):
    src = "x = 1\n"
    f = _make_file(tmp_path, "a.py", src)
    finding = _finding(str(f), 1, "vague_name", evidence="x is generic")
    rel = "a.py"
    baseline = {("vague_name", rel, 1, evidence_hash("vague_name", "x is generic"))}
    assert is_suppressed(finding, {}, set(), baseline, tmp_path) is True


def test_baseline_tuple_does_not_match_different_evidence(tmp_path: Path):
    src = "x = 1\n"
    f = _make_file(tmp_path, "a.py", src)
    finding = _finding(str(f), 1, "vague_name", evidence="DIFFERENT")
    baseline = {("vague_name", "a.py", 1, evidence_hash("vague_name", "x is generic"))}
    assert is_suppressed(finding, {}, set(), baseline, tmp_path) is False


def test_write_then_load_baseline_roundtrip(tmp_path: Path):
    findings = [
        _finding(str(tmp_path / "a.py"), 5, "vague_name", "x is generic"),
        _finding(str(tmp_path / "sub" / "b.py"), 7, "duplicate_code", "dupes 2"),
    ]
    (tmp_path / "sub").mkdir()
    bp = tmp_path / "posd-lint.baseline"
    n = write_baseline(bp, findings, tmp_path)
    assert n == 2
    loaded = load_baseline(bp)
    assert len(loaded) == 2
    for f in findings:
        assert is_suppressed(f, {}, set(), loaded, tmp_path) is True


def test_inline_ignore_within_finding_range(tmp_path: Path):
    """A multi-line finding (line..end_line) honors the marker on any of those lines."""
    src = "class C:\n    pass  # posd-lint: ignore[shallow_class]\n"
    f = _make_file(tmp_path, "a.py", src)
    parsed = parse_file(f)
    assert parsed is not None
    inline, file_level = parse_inline_suppressions([parsed])
    finding = Finding(
        file=str(f), line=1, end_line=2,
        detector="shallow_class", title="t", evidence="e",
        rubric_ref="5", rubric_title="rt",
    )
    assert is_suppressed(finding, inline, file_level, set(), tmp_path) is True
