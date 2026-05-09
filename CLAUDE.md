# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`posd-lint` — static analysis tool that surfaces violations of the principles in John Ousterhout's *A Philosophy of Software Design*. Two-layer design: deterministic detectors for recall + optional Claude AI judge for precision. Phases 1–4 complete (24 detectors, 58 tests). The authoritative handover document is `PLAN.md`; read it for full architectural decisions, calibration map, and gap log.

## Common commands

```bash
# Editable install (with dev deps for tests)
pip install -e ".[dev]"

# Run all tests
python3 -m pytest tests/

# Run a single test
python3 -m pytest tests/test_detectors.py::test_overexposure_positive -v

# Run the linter on a directory (deterministic only — no API calls)
python3 -m posd_lint.cli path/to/code
# or via the installed entry point:
posd-lint path/to/code

# Run only specific detectors
posd-lint path/ --detectors shallow_class,wide_interface,info_leakage

# With Claude judge (set creds first)
export ANTHROPIC_API_KEY=sk-ant-...        # OR
export AZURE_FOUNDRY_API_KEY=... AZURE_FOUNDRY_ENDPOINT=https://...
posd-lint path/ --ai-judge claude --output report.md

# Lint only files changed vs a git ref
posd-lint path/ --diff origin/main

# Generate a baseline of current findings (suppresses them on subsequent runs)
posd-lint path/ --baseline-update

# Verbose / debug logs
posd-lint path/ -v   # info
posd-lint path/ -vv  # debug
```

The CLI exits with code `1` if any finding has `judge_verdict == REAL` (CI gating), `0` otherwise, `2` on argument errors.

**Calibration target.** All thresholds are tuned against `/home/swynn/Code/Time-Tracking-Agent/time-tracker/src/`. After any detector change, run `posd-lint /home/swynn/Code/Time-Tracking-Agent/time-tracker/src/ --ai-judge none` and sanity-check the finding count delta (current baseline: 136 findings).

## Architecture

### Two-layer design

The deterministic layer (`posd_lint/detectors/`) provides **recall** — every candidate matching a heuristic surfaces. The AI judge (`posd_lint/judge/`) provides **precision** — Claude reads each candidate against the relevant rubric section and marks real / borderline / false_positive. The two layers compose via the shared `Finding` dataclass; the judge mutates fields on the same instance the detector emitted.

`--ai-judge none` is a fully usable mode (no creds required). The Anthropic SDK is imported lazily inside `_build_client()` so missing creds don't break deterministic runs.

### Detectors split into two ABCs

- `Detector` (in `detectors/_base.py`) — per-file. Implements `detect(file: ParsedFile) -> Iterable[Finding]`.
- `ProjectDetector` (same file) — cross-file. Implements `detect_project(project: Project) -> Iterable[Finding]`.

Each subclass uses `@register` or `@register_project` to add itself to the global registry. `posd_lint/detectors/__init__.py` is the side-effect-import hub; adding a new detector requires importing its module there.

Per-file and project-level run as separate phases in the CLI: per-file runs against each `ParsedFile`, then (if any project detectors are enabled) a `Project` is built once across all files and project detectors run against it.

### The `Project` model (`project.py` + `_callgraph.py`)

Built once per CLI run. Lazy `cached_property` indexes:

- `imports_by_file`, `module_paths` — basic import graph.
- `classes_by_name`, `public_class_attributes` — class index + cross-file attribute reads.
- `call_graph: dict[str, set[str]]` — qualified caller → callees. Resolves `self.foo()`, typed-local `obj.foo()`, `module.foo()` via imports, and bare top-level calls. Approximate (recall < 1) by design.
- `call_sites` — per-call-site detail (used by `pass_through_variable` for arg position tracking).
- `external_calls`, `function_effects` — effect propagation. Effects come from `posd_lint/data/effects.toml` (curated registry of effectful symbols across stdlib + popular third-party libs); propagation uses Tarjan SCC contraction so it terminates on cyclic graphs.
- `_local_var_classes`, `_function_return_types` — receiver-type inference for cross-file detectors that need to know what class a variable holds. Conservative: only annotated params, constructor assignments, and return-annotated calls.

When extending `Project`, prefer adding a new `cached_property` over mutating existing methods. Detectors that don't need the project never trigger its construction.

### The judge (`judge/claude.py` + `judge/prompts.py`)

The `SYSTEM_PROMPT` is built at module import time as `<persona> + <full posd-reference.md> + <output schema>` (~45 KB). It's sent with `cache_control: {"type": "ephemeral"}`, so per-call cost on multi-finding runs drops to ~10× the cache read rate. The user prompt only contains the per-finding code excerpt + evidence + a section-number pointer like "Apply §5 to the following finding."

Output is strict JSON: `{"verdict", "reasoning", "recommendation"}`. Tolerant parser falls back to substring extraction if Claude wraps in fences. Failures (API error, malformed JSON, missing rubric section) leave the finding `UNJUDGED` with a diagnostic in `judge_reasoning`; the run never crashes for a single bad finding.

Two transport modes: direct Anthropic API (`ANTHROPIC_API_KEY`) and Azure AI Foundry (`AZURE_FOUNDRY_API_KEY` + `AZURE_FOUNDRY_ENDPOINT`). Selected by env vars in `_build_client()`.

**When modifying judge code**, invoke the `claude-api` skill before editing — the canonical Anthropic SDK shape (cache markers, message structure) shifts and the skill has the current form.

### Config, suppression, diff (`config.py`, `suppress.py`, `cli.py`)

- `posd-lint.toml` is discovered by walking parents from the target dir. Schema includes `[posd-lint]` (rubric override, `disabled` list), `[detectors.<name>]` (constructor kwargs), `[layers]`, `[allowed_imports]`, `[forbidden_imports]`. Per architectural decision D4, every detector exposes thresholds as `__init__` kwargs; the registry's `detectors_with_config()` helper uses `inspect.signature` to inject `config=` only into detectors that accept it.
- Suppression: inline `# posd-lint: ignore[detector_name]`, `# posd-lint: ignore` (any detector), or `# posd-lint: ignore-file` at file top. Plus a `posd-lint.baseline` file with tab-separated tuples `(detector, relpath, line, evidence_hash[:12])`. The hash is content-derived (`sha256(detector\0evidence)`), so line drift alone doesn't invalidate but real measurement changes do.
- `--diff <ref>` filters per-file detectors to changed `.py` files but still builds the `Project` from the full tree (cross-file detectors need the full graph) and post-filters their findings.

### Reference document

`posd_lint/data/posd-reference.md` is the rubric the judge uses. Every detector carries a `rubric_ref` (section number string, e.g. `"5"`). The judge looks up the section by number from the cached system prompt. **If you add a detector, set `rubric_ref` to the matching section in `posd-reference.md`** — `prompts.py:index_sections()` is what the judge uses; an unknown ref produces a fail-open `UNJUDGED` finding.

## Adding a new detector

1. Create `posd_lint/detectors/<name>.py` with a `Detector` (or `ProjectDetector`) subclass decorated with `@register` (or `@register_project`). Set `name`, `title`, `rubric_ref`, `rubric_title`. Expose thresholds as `__init__` kwargs with module-level defaults (architectural decision D4 — keeps `posd-lint.toml` overrides clean).
2. Add the module to the side-effect import block in `posd_lint/detectors/__init__.py`.
3. Add `tests/corpus/<name>_positive.py` (must produce ≥1 finding) and `tests/corpus/<name>_negative.py` (must produce 0). For project-level detectors use `tests/corpus_projects/<name>_yes/` with multi-file fixtures.
4. Add a parametrize entry to `tests/test_detectors.py` (per-file) or a dedicated test function (project-level — see `test_overexposure_positive` for the pattern).
5. Run pytest; tune thresholds against the calibration target (time-tracker). Per the rule of thumb in PLAN.md §7: prefer raising thresholds (less noise) over lowering (more recall) — the AI judge can downgrade verdicts but can't surface what the deterministic layer didn't emit.

## Common pitfalls

- `Detector` and `ProjectDetector` ABCs themselves appear in module `vars()`; the test parametrize filter excludes them via `cls.__module__ == module.__name__`. Preserve that check.
- `from __future__ import annotations` is used for `X | Y` syntax in Python 3.10. Keep it on new files.
- The `posd_lint.data` package needs to ship `posd-reference.md`, `effects.toml`, and `findings.schema.json` as package data (see `pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]`). When adding a new bundled data file, add a force-include entry.
- Project-level detector tests need real directory layouts — corpus must be multiple `.py` files under `tests/corpus_projects/<name>_yes/`, parsed via `iter_python_files()`.
- Don't mutate `Finding` after the judge runs — only the judge mutates `judge_*` fields. Detectors emit fresh `Finding` instances.
- Effect-tracking false positives: the matcher in `effects.py` is permissive (suffix matching, multiple candidate dotted forms) to handle method chains like `self.client.messages.create`. Collisions are possible — if a `pure_function_violation` finding looks wrong, check the matched effect symbol first.

## Where to look when something is wrong

- Tests pass but a detector misfires on real code → tune thresholds in the detector module's class-level constants; verify against the time-tracker baseline.
- Detector silently produces no findings → check it's registered in `detectors/__init__.py` and that `rubric_ref` matches a real section in `posd-reference.md`.
- Judge run produces all UNJUDGED → likely a creds issue (`_build_client()` raises) or a section-lookup miss; bump verbosity (`-vv`).
- Performance regression on large codebases → a detector is doing redundant `ast.walk`s. The `Project` cached_properties exist precisely so cross-file work is shared; reuse them.
- Config not applying → `load_config()` walks parents from the target path; verify the `posd-lint.toml` is at or above the target dir.
