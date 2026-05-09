# posd-lint — Project Plan & Handover

**Last updated:** 2026-05-08 (end of phase 3)
**Status:** Phases 1–3 complete. 16 detectors, 19 passing tests, ~2960 LOC. Ready for phase 4.
**Purpose of this document:** Self-contained record of what's built, why, and what's next. Written so a fresh context (no conversation history) can pick up the project and keep building without re-deriving any decision.

---

## Table of contents

1. [What this project is](#1-what-this-project-is)
2. [Quick start: verify the project is healthy](#2-quick-start)
3. [File-by-file map](#3-file-by-file-map)
4. [Detector roster (current 16)](#4-detector-roster)
5. [Coverage of PoSD red flags](#5-coverage-of-posd-red-flags)
6. [Architectural decisions log](#6-architectural-decisions-log)
7. [Calibration map (every threshold and why)](#7-calibration-map)
8. [Known limitations and gaps](#8-known-limitations-and-gaps)
9. [The bigger picture (philosophy linter vs architecture linter)](#9-the-bigger-picture)
10. [Phase 4 plan — ordered work items](#10-phase-4-plan)
11. [Phase 5+ horizon](#11-phase-5-horizon)
12. [Operational guide (running, judging, debugging)](#12-operational-guide)
13. [Open questions (decisions deferred)](#13-open-questions)

---

## 1. What this project is

**posd-lint** is a Python static-analysis tool that surfaces violations of the principles in John Ousterhout's *A Philosophy of Software Design* (1st ed. 2018, 2nd ed. 2021). The architecture has two layers:

- **Deterministic surfacer** (this repo's `posd_lint/detectors/`). AST + a project-wide cross-file model. Provides *recall* — surface every candidate matching a heuristic for one of PoSD's red flags.
- **AI judge** (`posd_lint/judge/`). Calls Claude with the relevant section of `posd-reference.md` plus the candidate's code excerpt; returns verdict (real/borderline/false-positive) and recommendation. Provides *precision* — filters out heuristic misfires and grounds advice in the rubric.

The deterministic layer is the heart; the judge is the polish. The tool is useful with `--ai-judge none` (just static analysis) and substantially better with `--ai-judge claude`.

**Reference document.** `posd-reference.md` (also bundled at `posd_lint/data/posd-reference.md`) is the rubric. It covers all 22 chapters of PoSD, both editions, in the operational format: framing → diagnostic → most common mistake. Detectors carry a `rubric_ref` field (e.g. `"5"`) that the judge uses to extract the matching `## 5. Deep vs. shallow modules` section.

**Calibration target.** All thresholds were tuned against `/home/swynn/Code/Time-Tracking-Agent/time-tracker/src/` — a real Python codebase (~45 files, Teams bot + Azure stack + Anthropic integration). The latest full run on it produces 96 findings (`time-tracker-report-phase3.md`).

---

## 2. Quick start

After context clear, run these to confirm the project is in working state:

```bash
cd /home/swynn/Code/coding

# 1. Tests should all pass.
python3 -m pytest tests/ -v
# Expect: 19 passed

# 2. Detector registry should show 16.
python3 -c "from posd_lint.detectors import all_detectors, all_project_detectors; print(f'Per-file: {len(all_detectors())}, Project: {len(all_project_detectors())}')"
# Expect: Per-file: 13, Project: 3

# 3. Smoke test — run on a small directory of itself.
python3 -m posd_lint.cli posd_lint/detectors/ --ai-judge none | head -20
# Expect: a finding summary table

# 4. Full run on the calibration target.
python3 -m posd_lint.cli /home/swynn/Code/Time-Tracking-Agent/time-tracker/src/ --ai-judge none --output /tmp/baseline.md
# Expect: "Wrote report to /tmp/baseline.md (96 findings)"
diff /tmp/baseline.md time-tracker-report-phase3.md
# Expect: no diff
```

If any of those drift, something regressed during the context clear's gap (unlikely — there shouldn't be any gap) or after subsequent edits.

**To enable the AI judge** (cost-incurring; outputs verdicts and recommendations):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# OR (Azure AI Foundry, which time-tracker uses):
export AZURE_FOUNDRY_API_KEY=... AZURE_FOUNDRY_ENDPOINT=https://...

python3 -m posd_lint.cli /path/to/code --ai-judge claude --output report.md
```

---

## 3. File-by-file map

Read these in roughly this order to grok the codebase:

```
posd-reference.md                    The rubric. Read first if you don't know PoSD.
README.md                            User-facing overview.
PLAN.md                              This file.

posd_lint/
├── __init__.py                      Just __version__ = "0.1.0"
├── cli.py                           Entry point. argparse + orchestration.
├── parse.py                         File walking, AST parsing, comment extraction.
├── findings.py                      Finding dataclass + Severity/JudgeVerdict enums.
├── project.py                       Project model — cross-file indexes for ProjectDetectors.
├── report.py                        Markdown + JSON renderer.
├── data/
│   ├── __init__.py                  Marker for importlib.resources.
│   └── posd-reference.md            Bundled copy of the rubric (loaded by judge).
├── judge/
│   ├── __init__.py                  Re-exports ClaudeJudge, JudgeConfig.
│   ├── claude.py                    Anthropic SDK + Azure Foundry; judge() per finding.
│   └── prompts.py                   Rubric loader, section index, prompt construction.
└── detectors/
    ├── __init__.py                  Registry — imports each detector module side-effect-style.
    ├── _base.py                     Detector + ProjectDetector ABCs; @register decorators.
    └── (16 detector files; see §4)

tests/
├── test_detectors.py                19 tests. Parametrized over corpus pairs + project corpora.
├── corpus/                          Per-file test fixtures (positive_*.py / negative_*.py).
└── corpus_projects/                 Multi-file test fixtures for project-level detectors.
```

**Key cross-cutting types:**

- `Finding` (`findings.py`) — emitted by detectors, mutated by the judge. Single record.
- `Detector` ABC (`detectors/_base.py`) — per-file. Implements `detect(file: ParsedFile) -> Iterable[Finding]`.
- `ProjectDetector` ABC (`detectors/_base.py`) — project-level. Implements `detect_project(project: Project) -> Iterable[Finding]`.
- `Project` (`project.py`) — built once per run, lazy cached_property indexes.
- `ParsedFile` (`parse.py`) — AST + raw source + 1-indexed lines + `excerpt()` helper.

---

## 4. Detector roster

### Per-file (Detector subclass) — 13 detectors

| # | Name | Rubric § | Severity | What it flags |
|---|---|---|---|---|
| 1 | `vague_name` | 13 | low | Generic identifiers (`data`, `result`, `manager`, `info`); numbered generics (`data2`); single-letter top-level names |
| 2 | `hard_to_describe` | 12 | low | Public functions/methods/classes with no docstring or stub-only docstring (<15 chars), excluding ≤3-line bodies |
| 3 | `config_explosion` | 9 | medium | Functions with ≥7 parameters or ≥5 optional parameters |
| 4 | `shallow_class` | 5 | medium | Pass-through subclasses (empty body, single base); classes whose public methods average <4 statements (walked) each |
| 5 | `wide_interface` | 5 | medium | Classes/Protocols with ≥12 public methods (excludes `TestCase`, `TeamsActivityHandler`, `ActivityHandler`) |
| 6 | `comment_repeats_code` | 12 | low | Inline comments where Jaccard word-overlap with the next code line ≥0.6 (excludes TODO/FIXME/XXX/NOTE/HACK markers and divider comments) |
| 7 | `pass_through_method` | 8 | medium | Method body is a single Return/Expr/Await of a Call where args are 1:1 forward of the wrapper's params |
| 8 | `conjoined_methods` | 10 | low | Private helper called by exactly one method (excluding dispatcher pattern: ≥5 single-use callees) with non-trivial body (≥3 stmts) |
| 9 | `special_general_mixture` | 10 | low | ≥2 `isinstance()` checks in functions whose name doesn't signal dispatch (excludes `dispatch_*`/`parse_*`/etc., `__dunders__`, `@singledispatch`) |
| 10 | `repurposed_variable` | 13 | low | Variable reassigned within a function body with a different inferred kind (`list`→`dict`, `str`→`int`, etc.); skips None-init pattern and aug-assign |
| 11 | `impl_leaks_into_interface` | 12 | low | Public docstrings containing implementation phrases (`internally`, `we use`, `under the hood`, `TODO`, `HACK`) or `self._private` references |
| 12 | `forwarded_parameter` | 8 | low | Parameter of a small wrapper function (≤6 walked stmts; ≥3 params; no `**kwargs`) used exactly once, only as a Call argument |
| 13 | `required_call_ordering` | 6 | low | Class with paired lifecycle methods (open/close, start/stop, begin/end, etc.) and no `__enter__`/`__exit__` (excludes dataclass, Enum, Protocol bases) |

### Project-level (ProjectDetector subclass) — 3 detectors

| # | Name | Rubric § | Severity | What it flags |
|---|---|---|---|---|
| 14 | `overexposure` | 5 | low | Module exports ≥10 public symbols, ≥3 importers each pull ≤2 (avg) |
| 15 | `temporal_decomposition` | 6 | medium | ≥3 pipeline-suffixed classes (Reader/Writer/Parser/Loader/Processor/Transformer/Validator/Formatter/Encoder/Decoder/Importer/Exporter/Builder/Compiler/Renderer/Serializer/Deserializer) clustered in one package directory |
| 16 | `info_leakage` | 6 | medium | Class's public attributes read from ≥4 external files spanning ≥3 distinct attrs (receiver type-inference covers annotated params + constructor assignments only) |

**How findings get the judge's section:** `Finding.rubric_ref` is the section number in `posd-reference.md`. The judge in `prompts.py:index_sections()` parses the doc on `## N. Title` regex and builds `{section_num: section_text}`. Per-finding prompt = system prompt + `RUBRIC SECTION:\n{section_text}\n---\nCODE EXCERPT...`.

---

## 5. Coverage of PoSD red flags

The reference's Appendix A lists 18 red flags. Status:

| # | Red flag (Appendix A) | Detector | State |
|---|---|---|---|
| 1 | Shallow module | `shallow_class` | ✓ |
| 2 | Information leakage | `info_leakage` | ✓ partial (recall-limited by type inference) |
| 3 | Temporal decomposition | `temporal_decomposition` | ✓ heuristic |
| 4 | Overexposure | `overexposure` | ✓ |
| 5 | Pass-through method | `pass_through_method` | ✓ |
| 6 | Pass-through variable | `forwarded_parameter` | ✓ intra-function only — cross-frame in phase 4 |
| 7 | Repetition (duplicate code) | — | ✗ **missing** — phase 4 / wave C |
| 8 | Special-general mixture | `special_general_mixture` | ✓ |
| 9 | Conjoined methods | `conjoined_methods` | ✓ |
| 10 | Configuration parameter as smell | `config_explosion` | ✓ |
| 11 | Comment repeats code | `comment_repeats_code` | ✓ |
| 12 | Implementation contaminates interface | `impl_leaks_into_interface` | ✓ |
| 13 | Vague name | `vague_name` | ✓ |
| 14 | Hard to pick a name | partial in `vague_name` (numbered suffixes) | ✗ **partial** — phase 4 / wave C |
| 15 | Hard to describe | `hard_to_describe` | ✓ |
| 16 | Non-obvious code | — | ✗ **missing** — phase 4 / wave C (cyclomatic complexity proxy) |
| 17 | Repurposed variable | `repurposed_variable` | ✓ |
| 18 | Required call ordering | `required_call_ordering` | ✓ |

**14 of 18 covered. 3 outright missing (repetition, non-obvious, fully hard-to-pick-name). 1 partial (info_leakage).**

---

## 6. Architectural decisions log

Each decision below is load-bearing — changing it would mean a non-trivial refactor. Recorded with rationale + trade-off so the next session doesn't re-derive.

### D1. Hybrid deterministic + AI judge

- **Decision:** Deterministic surfacer + AI judge as separate layers, joined by Finding.
- **Rationale:** Pure static analysis can't reduce concepts like "deep module" to syntax. Pure LLM is slow, expensive, and lossy on structure. Combining gives recall (det) + precision (AI).
- **Trade-off:** Adds a network dependency for full functionality; `--ai-judge none` is a usable fallback.

### D2. Two ABCs (Detector and ProjectDetector), two registries

- **Decision:** `Detector.detect(file)` and `ProjectDetector.detect_project(project)`. Both register; CLI runs both.
- **Rationale:** Per-file detectors don't need (and shouldn't pay for) project model construction. Forcing all detectors through a single signature would either (a) require all to take an unused `project=None` or (b) waste work building project for runs that only use per-file detectors.
- **Trade-off:** A detector that's *primarily* per-file but could *occasionally* benefit from project context (e.g., `wide_interface` knowing how many distinct importers use the class) currently can't access it. **Phase 4 may revisit:** add optional `project=None` parameter to `Detector.detect()`. Backward-compatible with all existing detectors.

### D3. Python `ast` (stdlib), not libcst or tree-sitter

- **Decision:** Parse with `ast.parse()`. For comments, use `tokenize.generate_tokens()` (also stdlib).
- **Rationale:** Zero deps for parsing layer. Anthropic SDK is the only third-party in the package's runtime.
- **Trade-off:** `ast` doesn't preserve comments (hence the separate `tokenize` pass) or formatting. **If we ever want to write fix patches, switch to libcst.** Postponed indefinitely — the current "findings + recommendations" mode doesn't need round-trippable trees.

### D4. Detector tunables as constructor parameters

- **Decision:** Every detector exposes its thresholds as `__init__` kwargs with class-level defaults as module constants.
- **Rationale:** Makes detectors tunable per-project without forking. Sets up phase 4's `posd-lint.toml` cleanly: config keys map to constructor kwargs.
- **Trade-off:** Some duplication between class constants and constructor signature. Acceptable.

### D5. Single Finding dataclass, judge mutates in place

- **Decision:** `Finding.judge_verdict` defaults to `UNJUDGED`. Judge sets it on the same instance.
- **Rationale:** No type proliferation; reports treat unjudged and judged uniformly.
- **Trade-off:** Findings aren't immutable. Acceptable — they have a single owner during the run.

### D6. Markdown + JSON outputs; markdown drops false positives by default

- **Decision:** `render_markdown()` filters out `JudgeVerdict.FALSE_POSITIVE` unless `--show-false-positives`. JSON includes everything.
- **Rationale:** Markdown is for humans (who don't want noise). JSON is for tooling (which might want to audit what the judge dismissed).

### D7. System prompt invariant + per-finding user prompt with rubric section

- **Decision:** Strict-JSON output schema: `{"verdict": ..., "reasoning": ..., "recommendation": ...}`. Tolerant parser falls back to substring extraction if JSON-decoding fails.
- **Rationale:** Strictly-typed output. Tolerance handles occasional malformations without crashing the run.
- **Trade-off:** ~1–3% of judge calls return malformed JSON in practice; those Findings end up `UNJUDGED` with diagnostic text in `judge_reasoning`.

### D8. Section-based rubric extraction (`## N. Title` regex)

- **Decision:** Build `dict[section_num, section_text]` on judge initialization. Each finding's `rubric_ref` is a section number.
- **Rationale:** Sending only the relevant section keeps prompt size bounded.
- **Trade-off:** Tied to the rubric's heading structure. **Phase 4 alternative (recommended):** send the full rubric in system prompt with prompt caching → smaller per-call prompt + cache savings (see §10, Wave A).

### D9. Anthropic direct + Azure Foundry transport modes

- **Decision:** `_build_client()` checks `ANTHROPIC_API_KEY` first, then `AZURE_FOUNDRY_API_KEY` + `AZURE_FOUNDRY_ENDPOINT`.
- **Rationale:** time-tracker (the calibration target) uses Foundry. Supporting both lets the user run the judge against their existing creds with no setup.

### D10. Lazy import of anthropic SDK

- **Decision:** `from anthropic import Anthropic` is inside `_build_client()`, not at module top.
- **Rationale:** `--ai-judge none` works without the SDK installed. The `anthropic` dep is in `pyproject.toml` regardless, but this lets us run in CI / containers without network.

### D11. Calibration target: time-tracker

- **Decision:** Every threshold tuned against `/home/swynn/Code/Time-Tracking-Agent/time-tracker/src/`. Reports saved as `time-tracker-report-phase{1,2,3}.md`.
- **Rationale:** Real codebase the user owns; they can audit every finding.
- **Trade-off:** Thresholds may need re-tuning on different codebases. Phase 4's config will let users override per-project.

### D12. Test corpus: positive + negative per detector; project corpora as mini-trees

- **Decision:** `tests/corpus/{detector}_positive.py` must produce ≥1 finding. `tests/corpus/{detector}_negative.py` must produce 0. Project detectors use `tests/corpus_projects/{name}/` with multi-file layouts.
- **Rationale:** Catches both regressions (silent false negatives) and over-eagerness (new false positives) cheaply.
- **Trade-off:** Doesn't lock down exact finding counts — drift in count isn't tested. By design: tightening thresholds shouldn't break tests if the canonical positive case still flags.

### D13. Dispatcher exemption in conjoined_methods

- **Decision:** A "caller" with ≥5 private-and-only-once-called callees is treated as a dispatcher; pairs originating from it are excluded.
- **Rationale:** Discovered during phase 2 calibration: `TimeTrackingAgent._execute_tool` + 10 `_tool_*` handlers blew up findings (46) with no signal. Tightened to 28 after exemption.
- **Trade-off:** A genuinely conjoined dispatcher (rare) won't flag. Acceptable.

### D14. forwarded_parameter is wrapper-only

- **Decision:** Only flag in functions with ≤6 walked statements.
- **Rationale:** Discovered during phase 3 calibration: 38 findings dropped to 13 once we required the function be a true wrapper. Larger functions that happen to forward a param are not the smell — they're doing real work and the forwarded arg is just preprocessing.
- **Trade-off:** Cross-function pass-through-variable (the deeper smell) isn't covered. Phase 4 / wave A.

### D15. No fix patches; recommendations only

- **Decision:** The judge writes a `recommendation` string. Tool does not edit code.
- **Rationale:** User explicitly chose "Findings + recommendations only" early. Lower risk; lower implementation cost.
- **Trade-off:** Loop is human-in-the-middle. Phase 5 could add a separate `--fix` mode using libcst.

---

## 7. Calibration map

Every threshold currently in the codebase. Sources are module-level constants in each detector file; constructor params override.

| Detector | Constant | Value | Tuned against |
|---|---|---|---|
| `vague_name` | `GENERIC_NAMES` (frozenset) | 24 words | English + Python idiom; minor false positives on `value` in legitimate kv contexts |
| `hard_to_describe` | `SHORT_BODY_LINES` | 3 | Trivial getters/setters skipped |
| `hard_to_describe` | `MIN_DOCSTRING_CHARS` | 15 | Catches stubs like `"""Save."""` |
| `config_explosion` | `TOTAL_PARAM_THRESHOLD` | 7 | time-tracker `upsert_ticket` (13 params) flagged correctly |
| `config_explosion` | `OPTIONAL_PARAM_THRESHOLD` | 5 | Same |
| `shallow_class` | `BODY_NODES_PER_METHOD_THRESHOLD` | 4 | time-tracker `SQLiteStore` (pass-through) flagged; `TicketSyncService` not |
| `wide_interface` | `PUBLIC_METHOD_THRESHOLD` | 12 | time-tracker `TrackerStore` (22) flagged; `TimeEntryRepository` (5) not |
| `comment_repeats_code` | `SIMILARITY_THRESHOLD` | 0.6 | Jaccard on stemmed words minus stopwords |
| `comment_repeats_code` | `MIN_COMMENT_WORDS` | 2 | Tiny comments skipped |
| `pass_through_method` | (none — pure shape match) | — | Args must be 1:1 forward; transform exits |
| `conjoined_methods` | `TRIVIAL_BODY_THRESHOLD` | 3 | One-liner helpers exempt |
| `conjoined_methods` | `DISPATCHER_FANOUT_THRESHOLD` | 5 | See D13 |
| `special_general_mixture` | `ISINSTANCE_THRESHOLD` | 2 | Single isinstance is type-narrowing, not dispatch |
| `special_general_mixture` | `DISPATCH_NAME_PREFIXES` | 18 prefixes | `dispatch_*`, `parse_*`, etc. exempt |
| `repurposed_variable` | (kind set) | 9 kinds | list/dict/set/tuple/str/int/float/bool/none |
| `impl_leaks_into_interface` | `LEAK_PATTERNS` | 13 regex | `\binternally\b`, `\bunder the hood\b`, etc. |
| `forwarded_parameter` | `MIN_PARAMS` | 3 | 1-2 param functions ignored |
| `forwarded_parameter` | `MAX_WRAPPER_BODY_STMTS` | 6 | See D14 |
| `required_call_ordering` | `PAIRS` | 10 pairs | start/stop, open/close, etc. |
| `overexposure` | `THRESHOLD_EXPOSED` | 10 | Module exports |
| `overexposure` | `THRESHOLD_AVG_USED` | 2.0 | Avg per importer |
| `overexposure` | `MIN_IMPORTERS` | 3 | Single importer is just coupling |
| `temporal_decomposition` | `THRESHOLD_PIPELINE_CLASSES` | 3 | ≥3 pipeline classes in same dir |
| `temporal_decomposition` | `PIPELINE_SUFFIXES` | 17 suffixes | Reader/Writer/Parser/etc. |
| `info_leakage` | `THRESHOLD_EXTERNAL_READERS` | 4 | Distinct external files reading attrs |
| `info_leakage` | `THRESHOLD_DISTINCT_ATTRS` | 3 | Distinct attrs read across them |

**Rule of thumb when tuning:** prefer raising (less noise) over lowering (more recall). The AI judge can downgrade verdicts; it can't surface findings the deterministic layer didn't emit.

---

## 8. Known limitations and gaps

In rough priority order — addressing higher items unblocks more value.

### G1. No prompt caching in judge — wasteful at scale

Every judge call sends ~2k tokens of system prompt + a per-finding rubric section (~3k). On a 96-finding run that's ~480k tokens of system + section, mostly redundant. Anthropic supports prompt caching (`cache_control: {"type": "ephemeral"}`) for ~10% of cache-write cost on cache reads. **Strategy in §10, Wave A.**

### G2. forwarded_parameter is intra-function only

Real pass-through-variable per Ousterhout is data threaded through several layers. We flag the wrapper-only case. To catch the cross-frame case, we need a cross-module call graph. **Strategy in §10, Wave A.**

### G3. info_leakage receiver type-inference is conservative

Currently catches:
- Function params with annotation `x: ClassName`
- Module/local-level `x = ClassName(...)` constructor assignments

Doesn't catch:
- `for x in iter:` where `iter` is type-known
- `x = some_func()` where `some_func` has return-type annotation
- Attribute chain: `self.store.get(...)` where `get()` has return annotation

Recall is lower than it should be. time-tracker has 0 info_leakage findings; some are likely real but invisible to current heuristics. **Strategy in §10, Wave C.**

### G4. Three Appendix-A red flags missing

- **Repetition / duplicate code** — entirely absent. AST hash with normalized identifiers is the standard approach.
- **Hard to pick a name** — partial coverage in `vague_name` (numbered suffixes). Other patterns (`*_new`, `*_v2`, `*_fixed`, `process_actually`, etc.) aren't handled.
- **Non-obvious code** — `code should be obvious` (§17 of the rubric) has no detector. Cyclomatic-complexity proxy is the standard.

**Strategy in §10, Wave C.**

### G5. No declarative architecture rules

The user's "architecture linter" essay points to the qualitative gap: posd-lint applies *universal* PoSD principles. A team's *project-specific* rules (which layer can import which, which modules are public-API vs internal, etc.) aren't expressible. **Strategy in §10, Wave B.**

### G6. No effect tracking

Functions that touch I/O / network / DB / filesystem / global state aren't identified. Ousterhout's `calculate_invoice_total writes to the DB` smell is undetectable today. Hardest item; needs a curated effect ABI for stdlib + common third-party. **Strategy in §10, Wave D.**

### G7. No `--diff` mode

Tool always scans full directory. PR-mode (lint only changed files) would be valuable. Cheap to add. **§10, Wave E.**

### G8. No Claude Code skill packaging

Could ship as a `/posd-review` slash command. Needs a `SKILL.md` somewhere in `~/.claude/` or the project's `.claude/`. **§10, Wave E.**

### G9. No suppression / baselining

A team adopting posd-lint mid-project can't say "yes we know about that finding, accepted, don't show it again." Standard fix: a `# posd-lint: ignore[detector_name]` inline comment + tracker. **§10, Wave E.**

### G10. Comment_repeats_code only handles `#` comments, not docstrings

Docstrings that paraphrase the function body don't flag. Probably fine — `hard_to_describe` and `impl_leaks_into_interface` cover docstring quality from different angles — but worth noting.

### G11. No fix patches

By design (D15). If we ever want to switch, libcst is the path.

---

## 9. The bigger picture

The user articulated a vision in their last message before this plan: a typed property graph (Files/Modules/Classes/Functions/Variables/Imports/Types/Packages/Tests/Interfaces as nodes; imports/defines/calls/reads/writes/returns/instantiates/subclasses/implements/depends_on/mutates/catches/raises/exposes/hides/tests as edges) plus a declarative architecture-rules layer.

**Our tool is one branch of that vision.** Specifically:

| Their concept | Our coverage |
|---|---|
| AST | ✓ `ast` module + `ParsedFile` |
| Symbol graph | ~partial — `Project.classes_by_name`, `module_paths` |
| Import graph | ✓ basic — `Project.imports_by_file`; no cycle detection yet |
| Call graph | minimal — intra-class only (`conjoined_methods`); no cross-module |
| Type graph | minimal — receiver types in `info_leakage` only |
| Data-flow graph | ✗ |
| Control-flow graph | ✗ |
| Effect graph | ✗ — biggest representational gap |
| Test graph | ✗ |
| Ownership / boundary rules | ✗ — biggest *conceptual* gap |
| Declarative architecture config | ✗ |

**What we have that they don't emphasize:** the AI judge with the PoSD rubric. Their essay treats "good design review" as the unsolvable end-state ("Rice's theorem... cannot perfectly decide"). True formally; sidestepped practically — we use the LLM as a reader that applies principles to context. That's a real layer their sketch doesn't fully account for.

**Where their framing is sharper:** the architecture-rules layer is the load-bearing missing piece. The line *"code alone gives you facts; architectural intent gives you judgments"* is exactly right. PoSD gives us *universal* judgments (apply to any codebase). What they describe gives *project-specific* judgments (this layer must not import that one). They're complements, not alternatives.

**Phase 4's goal:** bridge from "philosophy linter" to "philosophy linter + architecture linter" by adding (a) the missing structural representations needed for both kinds of analysis, and (b) the declarative rules layer.

---

## 10. Phase 4 plan

Five waves. Within each wave, items can be built independently; cross-wave dependencies are noted. Order is "do A before B because B needs A's foundation."

---

### Wave A — Foundation upgrades (start here)

Foundation: cross-module call graph + prompt caching + import cycles. None of these are "detectors" per se; they upgrade the substrate that future detectors will rest on. Plus one immediately-shippable detector that the substrate enables.

#### A1. Add `Project.call_graph`

**Why first:** unblocks A4 (true pass-through-variable), C1 (effect tracking), and any future cross-module detector.

**Spec:**
- New `cached_property` on `Project`: `call_graph: dict[str, set[str]]` mapping qualified caller name → set of qualified callee names.
- Qualified name format: `module.qualname.function_name` (e.g. `tracker.agent.TimeTrackingAgent._execute_tool`).
- For each `ast.Call` node, resolve the target:
  - `self.foo()` → enclosing class's `foo` method (if exists).
  - `obj.foo()` where `obj` is a confidently-typed local (using same `_local_var_classes` heuristic from `info_leakage`) → that class's `foo` method.
  - `module.foo()` where `module` is a known import → `module.foo`.
  - Bare `foo()` where `foo` is a top-level name in this file → that name.
  - Otherwise: skip (unknown).
- Output is approximate; document that recall ≠ 1.

**Files to add/modify:**
- `posd_lint/project.py`: add `call_graph` cached_property + helper for qualified name resolution.
- New `posd_lint/_callgraph.py` if the helpers grow beyond ~80 LOC; otherwise inline.

**Estimate:** 200–300 LOC, 1 day.

**Acceptance criteria:**
- New test in `test_project.py` (new file): build call graph for `tests/corpus_projects/info_leakage_yes/` and verify expected edges.
- Performance: <1s on time-tracker (45 files).

#### A2. Prompt caching in the judge

**Why second:** every subsequent judge run benefits.

**Spec:**
- Switch from "system prompt + per-finding rubric section" to "system prompt = full rubric (cached) + per-finding user prompt referencing section by number."
- Use Anthropic's `cache_control: {"type": "ephemeral"}` on the system prompt.
- The system prompt becomes: `<persona text>\n\n<full posd-reference.md>\n\n<output schema>`. The user prompt becomes: `Apply §N to the following finding:\n\n<code excerpt>\n\n<detector evidence>`.
- The full rubric is ~15k tokens (~785 lines × ~75 chars). Cached after first call → ~10% cost on subsequent calls within the 5-min TTL.

**Files to modify:**
- `posd_lint/judge/prompts.py`: rewrite `SYSTEM_PROMPT` and `build_user_prompt`.
- `posd_lint/judge/claude.py`: pass `cache_control` markers to `messages.create`.

**Important:** when implementing this, **invoke the `claude-api` skill** (per its trigger rules — modifying a Claude feature like caching). The skill will give the canonical Anthropic SDK shape for cache markers.

**Estimate:** 100 LOC, ½ day. Test with a real judge run on time-tracker; verify cache hit rate ≥80% via Anthropic response usage metadata.

**Acceptance criteria:**
- Run produces same verdicts as before for a sample of 5 findings (regression check).
- Anthropic usage block shows `cache_creation_input_tokens` on first call, `cache_read_input_tokens` on subsequent calls.
- Total token spend reduced by ≥50% on a 96-finding run vs. pre-caching.

#### A3. `import_cycle` detector

**Why third:** trivial given existing `imports_by_file`.

**Spec:**
- New `ProjectDetector` in `detectors/import_cycle.py`.
- Build a directed graph: file → set of files it imports (resolve via `Project.module_paths`).
- Run Tarjan's SCC (stdlib `graphlib.TopologicalSorter` doesn't support cycles directly; write a small Tarjan or use `networkx` if we add it as a dep). Probably hand-write Tarjan — no new deps.
- For each SCC of size ≥2, emit one finding pointing at the smallest member with the others listed in `evidence`.
- Rubric ref: `6` (Information hiding vs. information leakage — cycles are dependency leaks).

**Files to add:**
- `posd_lint/detectors/import_cycle.py`.
- Register in `detectors/__init__.py` under "Phase 4 — project-level".
- Add test in `test_detectors.py` with a 3-file cycle corpus.

**Estimate:** 100 LOC, ½ day.

**Acceptance criteria:**
- Test fixture with `a.py → b.py → c.py → a.py` flags exactly one finding listing all three.
- A non-cycle dependency chain produces no finding.

#### A4. `pass_through_variable` detector (true cross-frame)

**Why fourth:** depends on A1.

**Spec:**
- New `ProjectDetector` in `detectors/pass_through_variable.py`.
- For each function param, walk the call graph 1–3 frames downstream. If the param is forwarded unchanged (no transform) through ≥2 frames before being read, flag.
- Effectively: `pass_through_method` extended across function boundaries.

**Files to add:**
- `posd_lint/detectors/pass_through_variable.py`.
- Register and add test corpus.

**Estimate:** 250 LOC, 1 day.

**Acceptance criteria:**
- A 3-function chain `outer(x) → middle(x) → leaf(x)` where `x` is read only in `leaf` flags `outer`'s param `x`.
- Same chain where `middle` reads `x` (`if x > 0: return ...`) doesn't flag.

**Wave A total:** 650–750 LOC, ~3 days.

---

### Wave B — Architecture rules layer (the qualitative leap)

This is the move from "philosophy linter" (universal PoSD principles) to "philosophy linter + architecture linter" (project-specific declared design). After this wave, `posd-lint` looks materially closer to the user's vision.

#### B1. `posd-lint.toml` config schema and loader

**Spec:**
- New `posd_lint/config.py` — TOML loader (use stdlib `tomllib`, Python 3.11+) returning a typed `Config` dataclass.
- Schema:

  ```toml
  # posd-lint.toml in project root
  [posd-lint]
  rubric = "posd-reference.md"  # override bundled rubric

  # Per-detector threshold overrides; key matches detector name.
  [detectors.config_explosion]
  total_threshold = 8       # raise from default 7
  optional_threshold = 6

  [detectors.wide_interface]
  threshold = 15

  # Skip these detectors entirely.
  disabled = ["repurposed_variable"]

  # Architecture rules — drive the new detectors below.
  [layers]
  domain  = ["app/domain/**"]
  service = ["app/services/**"]
  infra   = ["app/infrastructure/**"]

  [allowed_imports]
  # Layer X may import only these layers + stdlib.
  domain  = []
  service = ["domain"]
  infra   = ["domain", "service"]

  [forbidden_imports]
  # Specific module bans regardless of layer.
  "app/domain/**" = ["sqlalchemy", "requests", "flask", "django"]
  ```

- Config is loaded by `cli.py` if `posd-lint.toml` exists in the target directory or any ancestor up to `/`.

**Files to add:**
- `posd_lint/config.py`.
- Update `posd_lint/cli.py` to discover and apply config.
- Update each detector's `__init__` to accept its config (keep defaults; config overrides).

**Estimate:** 250 LOC, 1 day.

**Acceptance criteria:**
- Test fixture with a `posd-lint.toml` raising `wide_interface.threshold` to 25 silences time-tracker's `TrackerStore` finding.
- Disabled detectors don't run (verify via `--verbose`).

#### B2. `forbidden_import` detector

**Spec:**
- New `ProjectDetector` in `detectors/forbidden_import.py`.
- Reads `[forbidden_imports]` from config. For each pattern → list of forbidden module names, walk every file matching the pattern and check `imports_by_file`. Flag any matched import.
- Rubric ref: `6`.

**Estimate:** 100 LOC, ½ day.

#### B3. `boundary_violation` detector (layer-violation)

**Spec:**
- New `ProjectDetector` in `detectors/boundary_violation.py`.
- Reads `[layers]` and `[allowed_imports]` from config.
- For each file, identify its layer by glob-match. For each `from X import Y`, identify X's layer. If X's layer isn't in this file's layer's `allowed_imports`, flag.
- This is the "domain imported infra" case from the user's essay.
- Rubric ref: `6` or `8` (depends on framing — layer violation is both an info-hiding failure and a wrong-layer abstraction issue).

**Estimate:** 200 LOC, 1 day.

**Acceptance criteria:**
- Test fixture with `[layers] domain = ["pkg/domain/**"], infra = ["pkg/infra/**"]`, `[allowed_imports] domain = []`, and a file `pkg/domain/order.py` doing `from pkg.infra.db import session` flags one finding.
- Same fixture without the `from pkg.infra.db import session` line produces zero findings.

#### B4. `unstable_interface` detector (importer count without Protocol)

**Spec:**
- New `ProjectDetector` — flags classes that are imported by ≥N files but aren't behind a Protocol/ABC.
- Heuristic: class is imported (its name appears in `imports_by_file` values) by ≥10 distinct files, and there's no Protocol/ABC in the same module that the class inherits from.
- Rubric ref: `5` (Deep vs. shallow modules — high fan-in without an interface boundary signals coupling).

**Estimate:** 150 LOC, ½ day.

**Wave B total:** 700 LOC, ~3 days. **This is the biggest qualitative leap of phase 4.**

---

### Wave C — Coverage gaps (the missing 4 red flags)

Fills out PoSD red-flag coverage from 14/18 to 17/18.

#### C1. `duplicate_code` detector — fills "Repetition" (Appendix A #7)

**Spec:**
- New per-file `Detector` (could be project-level for cross-file dupes; start per-file).
- For each function/method body, compute a normalized AST hash:
  - Walk AST; for each node, record `(type_name, child_count)`.
  - Replace local variable names with positional placeholders (`_v0`, `_v1`, ...) so renamed-but-identical code still hashes the same.
  - Strip docstrings.
  - Hash the normalized sequence.
- Group functions by hash. Flag groups of size ≥2.
- Skip trivial functions (≤3 statements walked).
- Rubric ref: `10`.

**Files to add:**
- `posd_lint/detectors/duplicate_code.py`.
- `posd_lint/_ast_hash.py` for the normalization helper (testable independently).

**Estimate:** 250 LOC, 1–1.5 days.

**Acceptance criteria:**
- Two near-identical functions (same shape, different names) flag.
- Two functions of identical structure but different operations (e.g., `x + y` vs `x * y`) don't flag — the hash includes operation type.

#### C2. `cyclomatic_complexity` / non-obvious code — fills "Non-obvious code" (Appendix A #16)

**Spec:**
- New per-file `Detector`. For each function, count McCabe complexity (`if`/`elif`/`for`/`while`/`try`/`except`/`and`/`or`/`assert`/comprehension-`if`).
- Threshold: ≥10. Severity scales: 10–14 low, 15–19 medium, ≥20 high.
- Rubric ref: `17` (Code should be obvious).

**Files to add:**
- `posd_lint/detectors/cyclomatic_complexity.py`.

**Estimate:** 100 LOC, ½ day.

#### C3. Expand `vague_name` for "hard to pick a name" — fills Appendix A #14 fully

**Spec:**
- Extend existing `vague_name.py`. New patterns:
  - Versioned names: `process_v2`, `handler_new`, `User2`, `parse_actually`, `final_result`, `real_data`.
  - Adjective-only suffixes: `*_new`, `*_old`, `*_tmp`, `*_real`, `*_actual`, `*_final`, `*_v2`, `*_fixed`.
  - Differentiating-without-content suffixes: `*_helper`, `*_utility` on functions.
- These are "I couldn't think of a better name" tells.

**Files to modify:**
- `posd_lint/detectors/vague_name.py` — add new pattern recognition.
- Update positive corpus.

**Estimate:** 80 LOC, ½ day.

#### C4. Improve `info_leakage` type inference (fixes G3)

**Spec:**
- Extend `Project._local_var_classes` to also handle:
  - For-loop iteration: `for x in <expr>` where `<expr>` evaluates to a known typed iterable (best-effort: if `<expr>` is `obj.method()` and that method has return annotation `list[ClassName]` etc., bind `x` to `ClassName`).
  - Function-return assignments: `x = func()` where `func` has return annotation.
- This lifts info_leakage's recall on real codebases substantially.

**Files to modify:**
- `posd_lint/project.py` — extend `_local_var_classes` and add a `_function_return_types` cached_property.

**Estimate:** 200 LOC, 1 day.

**Wave C total:** 630 LOC, ~3 days.

---

### Wave D — Effect tracking (most ambitious; do last)

#### D1. `effect_db` — curated registry of effectful symbols

**Spec:**
- Static data file `posd_lint/data/effects.toml`:

  ```toml
  [filesystem]
  symbols = ["builtins.open", "io.open", "pathlib.Path.read_text", ...]

  [network]
  symbols = ["requests.get", "urllib.request.urlopen", "socket.socket", ...]

  [database]
  symbols = ["sqlite3.connect", "sqlalchemy.create_engine", ...]

  [global_state]
  symbols = ["os.environ", ...]
  ```

- ~300–500 entries covering stdlib + top-20 third-party libs.

#### D2. `function_effects` — propagate effects through call graph

**Spec:**
- Build (cached_property on Project): `function_effects: dict[qualname, set[Effect]]`.
- Direct effects: each function's set of effects from calls to symbols in `effect_db`.
- Transitive effects: walk `Project.call_graph` from each function, union the called functions' effects.

#### D3. `pure_function_violation` detector — flag promised-pure functions that aren't

**Spec:**
- Heuristic: a function whose name starts with `calculate_`, `compute_`, `parse_`, `format_`, `to_`, `as_`, `validate_`, etc., AND has effects beyond `pure` (computation only).
- Rubric ref: `12` / `13` (name doesn't match abstraction).

**Wave D total:** ~600 LOC + ~300 LOC of effect data, ~4–5 days.

This is genuinely hard. Defer until phases 1–C land.

---

### Wave E — Usability (do anytime)

These don't block anything; deliver them when convenient.

#### E1. `--diff` mode

`posd-lint --diff origin/main` runs all detectors against only changed `.py` files. For project-level detectors, build the Project from all files but only report findings in changed files.

**Estimate:** 150 LOC, ½ day.

#### E2. Suppression / baselining

Two mechanisms:
- Inline: `# posd-lint: ignore[detector_name]` at end of line.
- File-level baseline: `posd-lint.baseline` lists `(detector, file, line, evidence_hash)` tuples; matching findings are suppressed.

`posd-lint --baseline-update` regenerates the baseline from current findings.

**Estimate:** 250 LOC, 1 day.

#### E3. Claude Code skill: `/posd-review`

Package as a skill in `.claude/skills/posd-review/SKILL.md`. The skill prompt instructs Claude Code to run `posd-lint --output ... --ai-judge claude` against the current git diff and present findings inline.

**Estimate:** 50 LOC of skill definition + minor CLI tweaks.

#### E4. JSON Schema for output

Publish a JSON Schema for the `--format json` output. Lets downstream tools (CI dashboards, custom reports) consume findings safely.

**Estimate:** 50 LOC, ½ day.

---

### Phase 4 wave order summary

| Wave | Items | Total LOC | Days | Unblocks |
|---|---|---|---|---|
| A | Call graph; prompt caching; import_cycle; pass_through_variable | ~700 | 3 | Wave D, all cross-module work |
| B | Config; forbidden_import; boundary_violation; unstable_interface | ~700 | 3 | Architecture-linter use-case |
| C | duplicate_code; cyclomatic_complexity; vague_name expansion; info_leakage type inference | ~630 | 3 | Coverage gaps |
| D | effect_db; function_effects; pure_function_violation | ~900 | 5 | "Pretends-pure-but-isn't" findings |
| E | --diff; baselining; skill; JSON schema | ~500 | 2 | Usability |

**Recommended starting order:** A → B → C → E → D. Defer Wave D until everything else is stable; it's the riskiest engineering effort and produces value only after the others give a stable platform to evaluate against.

---

## 11. Phase 5+ horizon

Beyond phase 4, candidate directions (not planned in detail):

- **Multi-language support.** Tree-sitter for TS/JS/Go. Each language gets its own `parse_*.py` and detector adaptations. Fundamental architecture stays.
- **Library mode.** Expose `posd_lint` as a Python library so other tools can run detectors programmatically (CI dashboards, IDE integrations).
- **Watch mode.** `posd-lint watch path/` re-runs on file changes.
- **Output mode for AI agents.** A `--format claude-code` flag that emits findings in a shape Claude Code can consume directly as context for follow-up edits.
- **Custom detector loading.** Discover detectors from `posd-lint-plugins/` directory or via entry-points so teams can add project-specific rules without forking.
- **Codemod mode (libcst).** For each finding the judge marks "real" with high confidence, generate a libcst-backed patch the user can review/apply. Major undertaking — switches the parsing layer from `ast` to `libcst`.
- **Dashboard.** Web UI showing trend lines over commits: how many findings, which detectors are improving, etc. Out of scope for a CLI tool but a natural extension.

---

## 12. Operational guide

### Running the tool

```bash
# Pure deterministic (no API calls):
python3 -m posd_lint.cli /path/to/code

# Save markdown report:
python3 -m posd_lint.cli /path/to/code --output report.md

# JSON for tooling:
python3 -m posd_lint.cli /path/to/code --format json --output report.json

# Run only specific detectors:
python3 -m posd_lint.cli /path/to/code --detectors shallow_class,wide_interface,info_leakage

# With AI judge (Anthropic direct):
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m posd_lint.cli /path/to/code --ai-judge claude --output judged.md

# With AI judge (Azure Foundry):
export AZURE_FOUNDRY_API_KEY=... AZURE_FOUNDRY_ENDPOINT=https://...
python3 -m posd_lint.cli /path/to/code --ai-judge claude

# Verbose logging:
python3 -m posd_lint.cli /path/to/code -v       # info
python3 -m posd_lint.cli /path/to/code -vv      # debug
```

The CLI exits with code `1` if any finding has `judge_verdict == REAL` (useful for CI gating); `0` otherwise; `2` on argument errors.

### Running tests

```bash
python3 -m pytest tests/ -v              # all tests
python3 -m pytest tests/test_detectors.py::test_overexposure_positive -v   # single test
```

### Adding a new per-file detector

1. Create `posd_lint/detectors/my_detector.py`:

   ```python
   from typing import Iterable
   from posd_lint.detectors._base import Detector, register
   from posd_lint.findings import Finding, Severity
   from posd_lint.parse import ParsedFile

   @register
   class MyDetector(Detector):
       name = "my_detector"
       title = "My short title"
       rubric_ref = "5"  # section number in posd-reference.md
       rubric_title = "Deep vs. shallow modules"

       def detect(self, file: ParsedFile) -> Iterable[Finding]:
           # walk file.tree, yield Findings
           ...
   ```

2. Add to imports in `posd_lint/detectors/__init__.py`.
3. Create `tests/corpus/my_detector_positive.py` (must flag) and `tests/corpus/my_detector_negative.py` (must not).
4. Add a parametrize entry to `tests/test_detectors.py`.
5. Run tests; tune thresholds against the calibration target.

### Adding a new project-level detector

Same as above but use `ProjectDetector` and `register_project`. The `detect_project(project: Project)` method is called instead of `detect(file)`. For testing, create a directory under `tests/corpus_projects/` with the multi-file fixture and add a dedicated test that calls `_project_for(subdir)`.

### Common pitfalls

- **`Detector` abstract class showing up in `vars(module)`.** The test parametrize filter must check `cls.__module__ == module.__name__` to exclude the imported base. (Already in place.)
- **Project-level detector tests need real directory layouts.** You can't fake them with a single file string — the corpus is multiple `.py` files in a tree, parsed via `iter_python_files`.
- **`from __future__ import annotations` matters.** All detectors use it for `X | Y` syntax in 3.10. Keep it.
- **Don't mutate Findings after the judge runs.** Only the judge mutates `judge_*` fields; detectors emit fresh Findings.
- **Run pytest after every detector tweak.** The negative corpus catches false-positive regressions cheaply.

---

## 13. Open questions

Decisions that were deferred or noted for later. Each one would change something material if answered differently.

### Q1. Should per-file detectors get optional access to Project?

Currently no — `Detector.detect(file)` only sees the file. Some detectors would benefit from project context (`wide_interface` flagging only classes that are actually imported elsewhere, for example). Phase 4's call-graph work might make this worth revisiting.

**Proposed fix:** add `def detect(self, file: ParsedFile, project: Project | None = None)`. Backward-compatible. Project is built once if any detector needs it.

### Q2. Should the judge model be configurable?

Currently hard-coded to `claude-sonnet-4-6` in `JudgeConfig`. Reasonable default but not exposed via CLI. Probably should be: `--judge-model claude-opus-4-7` for high-stakes review.

### Q3. Should we ship our own Severity, or use a standard?

Right now `Severity` is custom. SARIF (the OASIS standard for static analysis output) has its own scheme. If we ever want to integrate with GitHub code scanning or other CI tools, we'll need SARIF output anyway. Defer until a real integration use-case appears.

### Q4. Threshold sources of truth: module constants vs config vs CLI flags

Currently three levels: module constant (default) → constructor kwarg (overridable). Phase 4 adds posd-lint.toml. The CLI doesn't currently expose per-detector flags; should it? Probably no — config file is cleaner. The CLI just toggles which detectors run.

### Q5. Anthropic SDK as required vs optional dep

In `pyproject.toml` it's required. Practically the tool runs without it via `--ai-judge none`. We could make `anthropic` an extras (`pip install posd-lint[claude]`). Defer; one dep is fine.

### Q6. The `Detector` ABC's static helpers

`is_public`, `function_param_names`, `function_default_count` are class-level statics on `Detector`. They're used by per-file detectors only. As more detectors are added in phase 4, these may grow. Consider moving to `_ast_helpers.py` if the count exceeds ~6.

### Q7. Test corpus discoverability

Corpus files are plain `.py` that look like real code. There's no marker indicating "this file is a test fixture." If someone runs `posd-lint` on the project root, it will lint its own corpus. Should we:
- Add a `# posd-lint: ignore-file` mechanism (would need it for E2 anyway)?
- Move corpus to a separate non-`.py` extension and load explicitly?

The first is the right answer; bundles with E2.

### Q8. False-positive rates by detector

Without running with the AI judge enabled (we never have, due to no creds in this env), we don't have hard FP-rate numbers per detector. Once judging runs, the JSON output's verdict distribution is the truth. Prioritize tuning the worst-FP-rate detectors. Likely candidates from intuition: `forwarded_parameter` and `conjoined_methods`. Likely already-tight: `pass_through_method` (very specific shape).

### Q9. The `claude-api` skill — when to invoke

The skill is available globally. Its trigger rules say invoke on Claude API code touches. Phase 4's prompt-caching work in A2 is a perfect trigger. **Reminder for the next session:** before editing `posd_lint/judge/claude.py` for caching, invoke the `claude-api` skill via the Skill tool — it has up-to-date Anthropic SDK details.

---

## Appendix: file inventory at handover time

```
/home/swynn/Code/coding/
├── PLAN.md                                      (this file)
├── README.md                                    user-facing overview
├── posd-reference.md                            the rubric (785 lines)
├── pyproject.toml                               package config
├── time-tracker-report.md                       phase 1 baseline (48 findings)
├── time-tracker-report-phase2.md                phase 2 (82 findings)
├── time-tracker-report-phase3.md                phase 3 latest (96 findings)
├── posd_lint/
│   ├── __init__.py                              5 lines
│   ├── cli.py                                   ~110 lines
│   ├── parse.py                                 ~110 lines
│   ├── findings.py                              ~50 lines
│   ├── project.py                               274 lines
│   ├── report.py                                119 lines
│   ├── data/posd-reference.md                   bundled rubric
│   ├── judge/
│   │   ├── claude.py                            161 lines
│   │   └── prompts.py                           98 lines
│   └── detectors/  (16 detectors, ~1700 lines total)
│       ├── _base.py                             94 lines
│       ├── (16 detector modules)
└── tests/
    ├── test_detectors.py                        19 tests
    ├── corpus/                                  22 fixture files
    └── corpus_projects/
        ├── overexposure_yes/                    multi-file pipeline-test
        ├── overexposure_no/
        ├── temporal_yes/
        └── info_leakage_yes/
```

Total Python source lines: ~2960 (per `wc -l`).

---

## End of plan

If you're picking this up after a context clear: read §1, §2, §3, then §10. That gets you oriented and pointing at the next work item. Everything else is reference for when you hit a question mid-implementation.
