"""Command-line entry point.

Usage:
    posd-lint <path> [--output report.md] [--ai-judge claude|none]
                     [--detectors d1,d2,...] [--rubric path/to/rubric.md]
                     [--format md|json] [--diff <ref>]
                     [--baseline-update]

Pipeline:
    1. Walk path, parse Python files.
    2. Run each enabled detector against each file, collecting Findings.
    3. Apply suppression (inline ignore comments + baseline file).
    4. If --ai-judge claude, send each surviving Finding to the judge.
    5. Render report (md or json) to stdout or --output file.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from posd_lint.config import load_config
from posd_lint.detectors import detectors_by_name, detectors_with_config
from posd_lint.findings import Finding
from posd_lint.parse import ParsedFile, iter_python_files, parse_file
from posd_lint.project import build_project
from posd_lint.report import render_json, render_markdown
from posd_lint.suppress import (
    BASELINE_FILENAME,
    baseline_path_for,
    is_suppressed,
    load_baseline,
    parse_inline_suppressions,
    write_baseline,
)


logger = logging.getLogger("posd_lint")


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"error: path does not exist: {target}", file=sys.stderr)
        return 2

    config = load_config(target)
    if config is not None:
        logger.info("Loaded config from %s", config.source_path)

    if args.detectors:
        names = [d.strip() for d in args.detectors.split(",") if d.strip()]
        per_file, project_dets = detectors_by_name(names)
    else:
        per_file, project_dets = detectors_with_config(config)
    logger.info(
        "Using %d per-file detectors, %d project detectors",
        len(per_file), len(project_dets),
    )

    rubric_override = (
        Path(args.rubric) if args.rubric
        else (config.rubric_path if config and config.rubric_path else None)
    )

    parsed_files = list(_parse_all(target))
    logger.info("Parsed %d files", len(parsed_files))

    diff_set: set[str] | None = None
    if args.diff:
        try:
            diff_set = _resolve_diff_files(target, args.diff)
        except _DiffError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        logger.info("--diff %s: %d changed .py file(s) in scope", args.diff, len(diff_set))

    project_root = target if target.is_dir() else target.parent

    per_file_targets = parsed_files
    if diff_set is not None:
        per_file_targets = [pf for pf in parsed_files if pf.path in diff_set]

    findings = _scan(per_file_targets, per_file)
    if project_dets:
        project = build_project(parsed_files, root=project_root)
        for det in project_dets:
            try:
                findings.extend(det.detect_project(project))
            except Exception as e:
                logger.warning("Project detector %s failed: %s", det.name, e)

    if diff_set is not None:
        before = len(findings)
        findings = [f for f in findings if f.file in diff_set]
        logger.info("--diff filter: %d → %d findings", before, len(findings))

    logger.info("Surfaced %d findings before suppression", len(findings))

    if args.baseline_update:
        baseline_file = project_root / BASELINE_FILENAME
        count = write_baseline(baseline_file, findings, project_root)
        print(
            f"Wrote {count} baseline entr{'y' if count == 1 else 'ies'} to {baseline_file}",
            file=sys.stderr,
        )
        return 0

    findings = _apply_suppressions(findings, parsed_files, project_root)
    logger.info("After suppression: %d findings", len(findings))

    if args.ai_judge == "claude" and findings:
        findings = _judge(findings, rubric_path=rubric_override)

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
    p.add_argument(
        "--diff",
        metavar="REF",
        default=None,
        help="Lint only .py files changed vs <REF> (e.g. origin/main). Project "
             "detectors still see the whole tree but report only on changed files.",
    )
    p.add_argument(
        "--baseline-update",
        action="store_true",
        help=f"Write current findings to {BASELINE_FILENAME} in the target directory and exit.",
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


def _apply_suppressions(
    findings: list[Finding],
    parsed_files: list[ParsedFile],
    project_root: Path,
) -> list[Finding]:
    inline_index, file_level = parse_inline_suppressions(parsed_files)
    baseline_file = baseline_path_for(project_root)
    baseline = load_baseline(baseline_file) if baseline_file else set()
    if baseline_file:
        logger.info("Loaded %d baseline entr%s from %s",
                    len(baseline), "y" if len(baseline) == 1 else "ies", baseline_file)
    return [
        f for f in findings
        if not is_suppressed(f, inline_index, file_level, baseline, project_root)
    ]


def _judge(findings: list[Finding], rubric_path: Path | None) -> list[Finding]:
    """Run findings through the Claude judge, in order. Sequential by design —
    rate limits and per-finding cost would make parallel only marginally faster."""
    from posd_lint.judge import ClaudeJudge, JudgeConfig
    judge = ClaudeJudge(JudgeConfig(rubric_path=rubric_path))
    for i, f in enumerate(findings):
        logger.info("Judging %d/%d: %s", i + 1, len(findings), f.location())
        judge.judge(f)
    return findings


class _DiffError(RuntimeError):
    pass


def _resolve_diff_files(target: Path, ref: str) -> set[str]:
    """Return absolute paths of .py files changed vs `ref` and under `target`."""
    start = target if target.is_dir() else target.parent
    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise _DiffError(f"--diff requires the target to be inside a git repo ({e})") from e

    repo_root = Path(toplevel)
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{ref}...HEAD", "--", "*.py"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
        names = result.stdout.splitlines()
    except subprocess.CalledProcessError:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", ref, "--", "*.py"],
                cwd=repo_root, capture_output=True, text=True, check=True,
            )
            names = result.stdout.splitlines()
        except subprocess.CalledProcessError as e:
            raise _DiffError(
                f"git diff failed for ref '{ref}': {e.stderr.strip() or e}"
            ) from e
    # Include uncommitted changes (working-tree + staged) vs HEAD.
    try:
        wt = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", "*.py"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
        names.extend(wt.stdout.splitlines())
    except subprocess.CalledProcessError:
        pass

    target_resolved = target.resolve()
    out: set[str] = set()
    for name in names:
        if not name.strip():
            continue
        abs_path = (repo_root / name).resolve()
        if not abs_path.exists():
            continue
        if target_resolved == abs_path or target_resolved in abs_path.parents:
            out.add(str(abs_path))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
