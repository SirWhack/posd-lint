# 05 — Open Questions & Decisions

Decisions that must be made before or early in implementation. Each carries a
recommendation, but the call is the owner's. Ordered by how much they constrain
everything downstream.

## Q1. Parser/type source — tree-sitter, compiler API, or hybrid?

**The dominating decision (see §2).** Tree-sitter is cheap, pure-Python, syntax
only; the TS compiler API (`ts-morph`) gives real types via a Node sidecar and
turns three detectors into upgrades over their Python versions.

**Recommendation:** **Hybrid, tree-sitter first.** Ship a complete tree-sitter-only
mode (Waves 0–2), then add the optional `--ts-types` sidecar (Waves 3–4) that
degrades gracefully when Node is absent — exactly the `--ai-judge none` pattern.
Reversible: the facade boundary means detectors don't care which tree they got.

## Q2. Shared detectors via a facade, or duplicate per language?

`PLAN.md` §11 reads as "duplicate per language." That's 24× drift surface.

**Recommendation:** **Shared, via a normalized-node facade** (§1). Strong external
precedent (Semgrep maps every language to one common AST). Detectors are written
once; language adapters translate. Allow a detector to declare applicable
languages so Python-idiom-bound ones (`required_call_ordering`) can opt out
cleanly rather than be forced into a meaningless TS mapping.

## Q3. How is TypeScript module resolution handled?

The project-level detectors live or die on a correct module graph. TS resolution
is genuinely involved: `baseUrl`, `paths`, `index.ts`, `.d.ts`, `export * from`,
`.mts`/`.cts`, monorepo references.

**Options:** (a) approximate, tree-sitter-only resolver covering the common cases;
(b) read `tsconfig.json` and implement the documented resolution algorithm;
(c) get resolution for free from the Option-B compiler sidecar.

**Recommendation:** Start with (a) for Wave 2 (covers most repos), and let (c)
supersede it when the Wave 3 sidecar lands. Scope `tsconfig` `paths` support
explicitly as the known risk in Wave 2.

## Q4. Is Node.js a hard dependency?

Only if/when we adopt Option B. Tree-sitter mode needs no Node.

**Recommendation:** Keep Node a **soft, mode-gated** dependency. Tree-sitter mode
installs clean (pure-Python wheels). The type-aware mode documents Node as a
prerequisite (extras-style), and the tool prints a clear "install Node for
`--ts-types`" notice instead of failing. Consistent with lazy-importing the
Anthropic SDK today (D10).

## Q5. How do we calibrate, with no TS equivalent of time-tracker?

Every Python threshold is tuned against one real codebase. TS needs the same.

**Recommendation:** Pick one real, owner-auditable mid-size TS project as the TS
calibration target and record its baseline finding count (the analog of
time-tracker's 136). Re-tune per-detector thresholds against it; do **not** assume
Python thresholds transfer (different idioms, different name conventions, no
dunders).

## Q6. Naming-convention scope — TS only, or JS too?

`tree-sitter-typescript` ships `typescript` + `tsx`; JS is essentially a subset.
Supporting `.js/.jsx` is nearly free structurally but JS lacks the type/visibility
signals that make several detectors *better* in TS.

**Recommendation:** Target TS/TSX first-class; accept JS/JSX opportunistically
through the same adapter, but don't tune or calibrate against JS in the first
pass. Document JS as "best-effort, syntax-only."

## Q7. Where does the facade live, and does Python migrate onto it?

Introducing the facade means the existing Python detectors *could* be refactored to
consume it too (Wave 0 does this for 3 as a faithfulness check).

**Recommendation:** Migrate Python detectors onto the facade **incrementally**, not
big-bang. Wave 0 proves 3; the rest migrate only as touched. The Python `ast`
adapter must stay behavior-identical (the existing corpus is the regression net).
Risk: a sloppy facade could regress Python findings — the positive/negative corpus
(D12) is the guardrail; run it on every facade change.

## Q8. Does this become its own phase in `PLAN.md`, or a fork?

Multi-language is currently a one-line "Phase 5+ horizon" item.

**Recommendation:** If greenlit, promote it to a real **Phase 5** section in
`PLAN.md` with the §4 waves, and add the facade decision to the architectural
decisions log (D-series). Keep this research dir as the backing detail the PLAN
entry points to.

## Q9. What about the `required_call_ordering` gap and other idiom mismatches?

A few detectors are Python-idiom-bound (context managers, dunders).

**Recommendation:** Don't force-fit. Let detectors declare applicable languages
(Q2). For `required_call_ordering`, either reframe around TS scoped-resource
constructs (`using`/`Symbol.dispose`, `try/finally`) as a *separate* TS detector
later, or simply mark it Python-only for now. Not worth blocking the rollout.

---

## Decision checklist (fill in before Wave 1)

- [ ] Q1 — Parser path chosen: ☐ tree-sitter only ☐ compiler API only ☐ **hybrid**
- [ ] Q2 — Detector strategy: ☐ **facade (shared)** ☐ duplicate per language
- [ ] Q3 — Module resolution approach for Wave 2 chosen
- [ ] Q4 — Node dependency policy chosen (hard vs. mode-gated)
- [ ] Q5 — TS calibration target selected
- [ ] Q6 — JS in scope? ☐ TS/TSX only ☐ + JS best-effort
- [ ] Q8 — Promote to `PLAN.md` Phase 5? ☐ yes ☐ keep as research only
