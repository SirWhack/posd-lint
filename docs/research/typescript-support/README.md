# Research: Adding TypeScript as a Linted Language

**Status:** Research / pre-decision. No code written. No commitment made.
**Date:** 2026-05-28
**Author:** Research spike (Claude)
**Scope:** Assess what it would take to make `posd-lint` lint TypeScript (and, by
extension, JavaScript) in addition to Python — the costs, the opportunities, the
strategic forks, and a phased plan if we decide to proceed.

This directory is a self-contained research package. It is written so that a
future implementer (or the project owner deciding whether to greenlight the
work) can read it cold and understand the full shape of the problem without
re-deriving the analysis.

---

## Reading order

| # | Document | What it answers |
|---|---|---|
| 0 | [`00-executive-summary.md`](./00-executive-summary.md) | The TL;DR: what transfers for free, what costs effort, the two decisions that dominate, and the recommended path. Read this first. |
| 1 | [`01-architecture-portability.md`](./01-architecture-portability.md) | Layer-by-layer: which parts of the current codebase are language-neutral and which are welded to Python's `ast`. Introduces the normalized-node facade. |
| 2 | [`02-parser-and-tooling-options.md`](./02-parser-and-tooling-options.md) | The central fork: tree-sitter (syntax only, pure Python) vs. the TypeScript compiler API via a Node sidecar (full types). Grounded in external research. |
| 3 | [`03-detector-portability-matrix.md`](./03-detector-portability-matrix.md) | All 24 detectors, classified by how cleanly each maps to TypeScript, with the specific adaptation each needs. |
| 4 | [`04-implementation-roadmap.md`](./04-implementation-roadmap.md) | A phased plan in the house style of `PLAN.md` — waves, LOC estimates, acceptance criteria. |
| 5 | [`05-open-questions-and-decisions.md`](./05-open-questions-and-decisions.md) | The decisions that must be made before/early in implementation, with recommendations. |

## One-paragraph summary

`posd-lint`'s two-layer design (deterministic detectors for recall + AI judge for
precision) is already ~40% language-neutral: the **AI judge, the PoSD rubric, the
`Finding` model, reporting, config, suppression, baselining, and `--diff` carry
over to TypeScript with little or no change.** The work concentrates in three
places: a new **parse layer**, a new **`Project`/call-graph model**, and
**adapting the 24 detectors** (most of which encode language-neutral *concepts*
but are coded against Python AST node types). The single decision that most
shapes the result is the **parser/type-info choice** (§2): a syntax-only
tree-sitter path is cheap and covers ~15 detectors, while a TypeScript-compiler
path costs a Node.js sidecar but makes the type-hungry detectors *better than
their Python counterparts*. The second decision is whether detectors are
**shared via a normalized-node facade** (recommended — this is how Semgrep stays
"loosely coupled" per language) or **duplicated per language** (24× drift).

> This is analysis only. Nothing here has been built, and no irreversible choice
> has been made. The roadmap (§4) is a proposal, not a schedule.
