"""Command-line entry point.

Usage:
    posd-lint <path> [--output report.md] [--ai-judge claude|none]
                     [--detectors d1,d2,...] [--rubric path/to/rubric.md]
                     [--format md|json]

Pipeline:
    1. Walk path, parse Python files.
    2. Run each enabled detector against each file, collecting Findings.
    3. If --ai-judge claude, send each Finding to the judge for verdict + recommendation.
    4. Render report (md or json) to stdout or --output file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from posd_lint.detectors import all_detectors, all_project_detectors, detectors_by_name
from posd_lint.findings import Finding
from posd_lint.parse import ParsedFile, iter_python_files, parse_file
from posd_lint.project import build_project
from posd_lint.report import render_json, render_markdown


logger = logging.getLogger("posd_lint")


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"error: path does not exist: {target}", file=sys.stderr)
        return 2

    if args.detectors:
        names = [d.strip() for d in args.detectors.split(",") if d.strip()]
        per_file, project_dets = detectors_by_name(names)
    else:
        per_file = all_detectors()
        project_dets = all_project_detectors()
    logger.info(
        "Using %d per-file detectors, %d project detectors",
        len(per_file), len(project_dets),
    )

    parsed_files = list(_parse_all(target))
    logger.info("Parsed %d files", len(parsed_files))

    findings = _scan(parsed_files, per_file)
    if project_dets:
        project = build_project(parsed_files, root=target if target.is_dir() else target.parent)
        for det in project_dets:
            try:
                findings.extend(det.detect_project(project))
            except Exception as e:
                logger.warning("Project detector %s failed: %s", det.name, e)
    logger.info("Surfaced %d findings before AI review", len(findings))

    if args.ai_judge == "claude" and findings:
        findings = _judge(findings, rubric_path=Path(args.rubric) if args.rubric else None)

    output = (
        render_json(findings) if args.format == "json"
        else render_markdown(findings, include_false_positives=args.show_false_positives)
    )

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Wrote report to {args.output} ({len(findings)} findings)", file=sys.stderr)
    else:
        print(output)

    return 1 if any(f.judge_verdict.value == "real" for f in findings) else 0


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="posd-lint",
        description="Surface PoSD red flags in Python code; optionally judge with Claude.",
    )
    p.add_argument("path", help="File or directory to analyze")
    p.add_argument(
        "--ai-judge",
        choices=["claude", "none"],
        default="none",
        help="Run findings through the AI judge (default: none — deterministic only)",
    )
    p.add_argument("--detectors", help="Comma-separated detector names. Default: all.")
    p.add_argument("--output", help="Write report to this file instead of stdout")
    p.add_argument("--format", choices=["md", "json"], default="md", help="Output format (default: md)")
    p.add_argument("--rubric", help="Override the bundled posd-reference.md")
    p.add_argument(
        "--show-false-positives",
        action="store_true",
        help="Include findings the judge marked false positive in the markdown report",
    )
    p.add_argument("-v", "--verbose", action="count", default=0, help="Repeat for debug logging")
    return p


def _configure_logging(verbose: int) -> None:
    level = logging.WARNING if verbose == 0 else logging.INFO if verbose == 1 else logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _parse_all(root: Path) -> list[ParsedFile]:
    """Walk root, parse every Python file. Skips files with syntax errors."""
    out: list[ParsedFile] = []
    for path in iter_python_files(root):
        parsed = parse_file(path)
        if parsed is None:
            logger.debug("Skipping unparseable: %s", path)
            continue
        out.append(parsed)
    return out


def _scan(files: list[ParsedFile], detectors) -> list[Finding]:
    """Run every per-file detector against every parsed file."""
    findings: list[Finding] = []
    for parsed in files:
        for det in detectors:
            try:
                findings.extend(det.detect(parsed))
            except Exception as e:
                logger.warning("Detector %s failed on %s: %s", det.name, parsed.path, e)
    return findings


def _judge(findings: list[Finding], rubric_path: Path | None) -> list[Finding]:
    """Run findings through the Claude judge, in order. Sequential by design —
    rate limits and per-finding cost would make parallel only marginally faster."""
    from posd_lint.judge import ClaudeJudge, JudgeConfig
    judge = ClaudeJudge(JudgeConfig(rubric_path=rubric_path))
    for i, f in enumerate(findings):
        logger.info("Judging %d/%d: %s", i + 1, len(findings), f.location())
        judge.judge(f)
    return findings


if __name__ == "__main__":
    raise SystemExit(main())
