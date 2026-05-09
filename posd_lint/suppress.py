"""Suppression: inline `# posd-lint: ignore` comments + `posd-lint.baseline` files.

Two independent layers:

- Inline: per-line `# posd-lint: ignore[name1,name2]` (or bare `# posd-lint: ignore`)
  silences findings on that line; `# posd-lint: ignore-file` at file level silences
  every finding in the file.
- Baseline: a tab-separated file `posd-lint.baseline` listing
  `(detector, relpath, line, evidence_hash)` tuples. Findings whose tuple matches
  are dropped. Use `--baseline-update` to (re)generate from current findings.

The baseline is keyed on a stable hash of `(detector, evidence)` so that line drift
alone doesn't invalidate entries — but a real change to the evidence (e.g. method
count went from 12 to 14) does, on purpose: the finding has materially changed.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from posd_lint.findings import Finding
from posd_lint.parse import ParsedFile, extract_comments


BASELINE_FILENAME = "posd-lint.baseline"

# `# posd-lint: ignore[a, b]`  → group(1) = "a, b"
# `# posd-lint: ignore`        → group(1) = None
_INLINE_RE = re.compile(r"posd-lint\s*:\s*ignore(?:\[([^\]]*)\])?")
_FILE_RE = re.compile(r"posd-lint\s*:\s*ignore-file")


def evidence_hash(detector: str, evidence: str) -> str:
    """Stable 12-char hash; baselines store this so re-formatting evidence
    text in a detector won't silently invalidate every entry — but a real
    measurement change (e.g. param count) will."""
    h = hashlib.sha256(f"{detector}\0{evidence}".encode("utf-8")).hexdigest()
    return h[:12]


# Per-file inline index. None = "any detector silenced on this line".
InlineIndex = dict[str, dict[int, set[str] | None]]
FileLevelSet = set[str]


def parse_inline_suppressions(
    parsed_files: Iterable[ParsedFile],
) -> tuple[InlineIndex, FileLevelSet]:
    """Scan each file's comments for ignore directives.

    Returns:
        line_index: file_path → {line_no → set of detector names | None for "all"}
        file_level: set of file_paths fully suppressed via `ignore-file`
    """
    line_index: InlineIndex = {}
    file_level: FileLevelSet = set()

    for pf in parsed_files:
        for ct in extract_comments(pf.source):
            if _FILE_RE.search(ct.text):
                file_level.add(pf.path)
                continue
            m = _INLINE_RE.search(ct.text)
            if not m:
                continue
            names_group = m.group(1)
            if names_group is None:
                names: set[str] | None = None
            else:
                names = {n.strip() for n in names_group.split(",") if n.strip()}
                if not names:
                    names = None
            per_line = line_index.setdefault(pf.path, {})
            existing = per_line.get(ct.line, set())
            if existing is None or names is None:
                per_line[ct.line] = None
            else:
                per_line[ct.line] = existing | names
    return line_index, file_level


# Baseline tuples: (detector, relative_path, line, evidence_hash).
BaselineEntry = tuple[str, str, int, str]


def baseline_path_for(target: Path) -> Path | None:
    """Find `posd-lint.baseline` in target dir or any ancestor."""
    start = target if target.is_dir() else target.parent
    for d in [start, *start.parents]:
        candidate = d / BASELINE_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_baseline(path: Path) -> set[BaselineEntry]:
    """Read a baseline file. Lines are tab-separated; blanks and `#` comments skipped."""
    out: set[BaselineEntry] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        det, rel, lineno, ev = parts
        try:
            out.add((det, rel, int(lineno), ev))
        except ValueError:
            continue
    return out


def write_baseline(path: Path, findings: list[Finding], root: Path) -> int:
    """Write a deterministic (sorted) baseline file. Returns the count written."""
    entries: set[BaselineEntry] = set()
    for f in findings:
        rel = _relpath(f.file, root)
        entries.add((f.detector, rel, f.line, evidence_hash(f.detector, f.evidence)))
    sorted_entries = sorted(entries)
    lines = [
        "# posd-lint baseline — suppressed findings.",
        "# Format: detector<TAB>relative_path<TAB>line<TAB>evidence_hash",
        "# Regenerate with `posd-lint --baseline-update`.",
    ]
    lines.extend("\t".join((d, r, str(ln), ev)) for d, r, ln, ev in sorted_entries)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(sorted_entries)


def is_suppressed(
    finding: Finding,
    inline_index: InlineIndex,
    file_level: FileLevelSet,
    baseline: set[BaselineEntry],
    root: Path,
) -> bool:
    if finding.file in file_level:
        return True
    per_line = inline_index.get(finding.file)
    if per_line is not None:
        for ln in _candidate_lines(finding):
            entry = per_line.get(ln, "absent")
            if entry == "absent":
                continue
            if entry is None or finding.detector in entry:  # type: ignore[operator]
                return True
    if baseline:
        rel = _relpath(finding.file, root)
        key = (finding.detector, rel, finding.line, evidence_hash(finding.detector, finding.evidence))
        if key in baseline:
            return True
    return False


def _candidate_lines(finding: Finding) -> Iterable[int]:
    """Lines the user could plausibly attach the inline marker to.

    A finding spans line..end_line; an `# ignore` on any of those lines counts.
    """
    if finding.end_line and finding.end_line >= finding.line:
        return range(finding.line, finding.end_line + 1)
    return (finding.line,)


def _relpath(file: str, root: Path) -> str:
    try:
        return str(Path(file).resolve().relative_to(root.resolve()))
    except ValueError:
        return file
