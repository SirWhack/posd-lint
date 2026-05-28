# 04 — Implementation Roadmap (proposal)

A phased plan in the house style of `PLAN.md`. **This is a proposal, not a
commitment** — LOC estimates are order-of-magnitude, and each wave is gated on the
prior one proving out. The ordering follows the project's own rule: ship cheap
value first, defer the riskiest engineering (call graph + types) to last.

## Pre-work: one decision gate

Before Wave 1, settle **Decision 1** (§2: parser/type source) and **Decision 2**
(§1: facade vs. duplicate detectors). The recommended answers are *hybrid,
tree-sitter first* and *shared detectors via a facade*. The Wave 0 spike exists to
confirm them with code before committing.

---

## Wave 0 — Spike & seam (de-risk the two decisions)

**Goal:** prove the normalized-node facade against real TS, on the cheapest
detectors, with tree-sitter only.

- Add `posd_lint/lang/` package: `lang/base.py` (the facade dataclasses from §1),
  `lang/python/adapter.py` (wrap existing `ast`-based extraction behind the
  facade), `lang/typescript/adapter.py` (tree-sitter → facade).
- Port **2–3 purely structural detectors** to consume the facade instead of
  `ast`: suggested `cyclomatic_complexity`, `config_explosion`, `wide_interface`.
- Wire `parse.py` / `cli.py` to dispatch by file extension to the right adapter.

**Acceptance:**
- The 3 ported detectors pass their existing Python corpus tests *through the
  facade* (proves the Python adapter is faithful — no regression).
- The same 3 detectors produce correct findings on a small TS fixture
  (`tests/corpus_ts/`).
- No new runtime dependency beyond `tree-sitter` + `tree-sitter-typescript`.

**Estimate:** ~400–600 LOC, ~3–4 days. **This wave is the real go/no-go.**

---

## Wave 1 — Structural TS detectors (the shippable core)

**Goal:** a complete, useful TS lint mode on tree-sitter alone.

- Finish the facade (visibility, doc-comment, parameter models from §3's
  cross-cutting list).
- Port the remaining **Clean/Better per-file detectors**: `vague_name`,
  `shallow_class`, `comment_repeats_code`, `pass_through_method`,
  `forwarded_parameter`, `duplicate_code`, plus the **Adapt** ones that don't need
  types: `hard_to_describe`, `conjoined_methods`, `special_general_mixture`,
  `impl_leaks_into_interface`.
- TS comment extraction via tree-sitter CST (replaces the `tokenize` pass).
- TS inline-suppression syntax (`// posd-lint: ignore[...]`).

**Acceptance:**
- Each ported detector has a `tests/corpus_ts/<name>_positive.ts` (≥1 finding) and
  `_negative.ts` (0), mirroring the Python corpus discipline (D12).
- A full run on a real mid-size TS project produces a sane finding count (pick a
  TS calibration target analogous to time-tracker).
- The AI judge runs against TS findings unchanged (it's language-neutral).

**Estimate:** ~1,000–1,400 LOC, ~6–8 days.

---

## Wave 2 — TS Project model & import-graph detectors

**Goal:** cross-file analysis that doesn't need a full call graph.

- Build `lang/typescript` project indexes: module graph from `import`/`export`,
  honoring `tsconfig.json` (`baseUrl`, `paths`, re-exports). Decide build-vs-buy
  on resolution (Option A heuristic vs. lean on a resolver lib).
- Port the **import-graph project detectors**: `overexposure`,
  `temporal_decomposition`, `forbidden_import`, `boundary_violation`,
  `unstable_interface`, `import_cycle` (Tarjan reused; only the graph input is new).

**Acceptance:**
- `import_cycle` flags a 3-file TS cycle fixture and stays silent on a DAG.
- `boundary_violation` honors the existing `posd-lint.toml` layer config against a
  TS fixture (config schema unchanged).

**Estimate:** ~800–1,000 LOC, ~5–7 days. **`tsconfig` resolution is the risk
here** — scope it explicitly.

---

## Wave 3 — Optional type-aware mode (the upgrade)

**Goal:** the three type-hungry detectors, *better than their Python versions*.

- Add the optional **Node/`ts-morph` sidecar** (`--ts-types`): a subprocess that
  type-checks the program once and emits a type-enriched facade over JSON/stdout.
  Degrades gracefully to tree-sitter-only when Node is absent (mirrors
  `--ai-judge none`).
- Enrich the facade with resolved types + symbol graph.
- Upgrade `info_leakage` (fixes G3), `repurposed_variable`; build the TS call
  graph for `pass_through_variable`.

**Acceptance:**
- `info_leakage` recall on the TS calibration target visibly exceeds the
  tree-sitter-only baseline.
- Graceful degradation verified: same run without Node still works (no crash,
  type-aware detectors simply skipped with a notice).

**Estimate:** ~900–1,200 LOC + sidecar (~300 LOC JS), ~8–10 days. **Highest risk;
do last.**

---

## Wave 4 — Effects for TS + `pure_function_violation`

**Goal:** the effect-tracking detector for TS.

- Author a TS/Node/browser/npm effects registry (sibling to `effects.toml`):
  `fs`, `node:fs/promises`, `fetch`/`axios`, `console`, DB drivers, etc.
- Reuse `effects.py`'s Tarjan propagation verbatim over the Wave 3 call graph.
- Port `pure_function_violation` with TS purity-name conventions.

**Acceptance:**
- A TS function named `calculateTotal` that calls `fs.writeFileSync` flags; a pure
  one doesn't.

**Estimate:** ~300 LOC code + ~300 LOC registry data, ~3–4 days.

---

## Wave order summary

| Wave | Theme | Depends on | Parser | LOC (≈) | Days (≈) |
|---|---|---|---|---|---|
| 0 | Spike + facade seam | — | tree-sitter | 400–600 | 3–4 |
| 1 | Structural detectors | 0 | tree-sitter | 1,000–1,400 | 6–8 |
| 2 | Project / import graph | 1 | tree-sitter | 800–1,000 | 5–7 |
| 3 | Type-aware mode | 1 (2 helps) | + Node sidecar | 900–1,200 (+300 JS) | 8–10 |
| 4 | Effects + purity | 3 | + Node sidecar | 600 | 3–4 |

**Total to full parity+upgrade:** ~3,700–4,800 LOC, ~5–7 weeks of focused work.
**Total to a genuinely useful tree-sitter-only TS mode (Waves 0–2):** ~2,200–3,000
LOC, ~2.5–3.5 weeks — and that's a shippable milestone on its own.

## Testing & calibration notes (carry the existing discipline)

- Keep the positive/negative corpus rule (D12): every TS detector needs a
  `corpus_ts/<name>_{positive,negative}.ts` pair.
- Pick a **TS calibration target** the owner can audit, analogous to time-tracker
  for Python. Re-tune thresholds against it; prefer raising over lowering (PLAN §7).
- The judge and rubric need no TS-specific changes — a TS finding is judged with
  the same rubric section as its Python equivalent.
- Package-data discipline: a TS `effects.toml` and any bundled grammar artifacts
  need `force-include` entries in `pyproject.toml` (per CLAUDE.md pitfalls).
