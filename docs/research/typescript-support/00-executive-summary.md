# 00 — Executive Summary

## The opportunity in one sentence

PoSD's principles are language-universal, the AI judge that applies them is
already language-agnostic, and roughly 40% of `posd-lint`'s machinery doesn't
care what language it's looking at — so adding TypeScript is mostly a matter of
**a new parse layer + a new project model + adapting (not rewriting) the
detectors**, and for the type-hungry detectors TypeScript actually offers a
*better* result than Python.

## What transfers for free

These layers have zero or near-zero language coupling and come along essentially
unchanged:

- **The AI judge** (`judge/`). It reads a code excerpt + a rubric section and
  returns a verdict. It never inspects an AST. The rubric
  (`posd_lint/data/posd-reference.md`, 454 lines) mentions Python only twice.
- **The output model.** `Finding`, `Severity`, `JudgeVerdict` are string-based
  records with no language assumptions.
- **Reporting** (`report.py`), **config** (`config.py`), **suppression /
  baselining** (`suppress.py`), and the **`--diff` flow** are all
  language-agnostic. (`SKIP_DIRS` in `parse.py` already excludes `node_modules`
  — someone was already thinking about a JS/TS world.)

## What costs effort

Concentrated in three areas:

1. **Parse layer** (`parse.py`). `ParsedFile` wraps `ast.Module` directly;
   `iter_python_files` is hardcoded to `.py`; comments come from `tokenize`.
   This is a rebuild, not an edit.
2. **Project model** (`project.py`, `_callgraph.py`, `effects.py`/`effects.toml`).
   Cross-file indexes, call-graph resolution, and the effect registry are all
   built on Python's module system and `ast`. This is the hardest part —
   especially call-graph + module resolution.
3. **Detectors** (`detectors/`). 19 of 24 import `ast`; ~360 references to
   `ast.*` node types. But the *concepts* are mostly language-neutral — see the
   matrix in §3. ~17 of 24 map straightforwardly; ~2 are genuinely hard
   (`import_cycle`, `pass_through_variable`) because they lean on the call/module
   graph.

## The two decisions that dominate everything

### Decision 1 — Parser / type-info source (see §2)

| | **Tree-sitter** (syntax only) | **TS compiler API via Node sidecar** (full types) |
|---|---|---|
| Type resolution | ❌ none | ✅ full (`getTypeChecker()`) |
| Runtime deps | Pure-Python wheels (`py-tree-sitter`) | Node.js sidecar + IPC |
| Speed | Very fast | Slower (type-checking a program) |
| Detector coverage | ~15 structural detectors | All, and 3 become *better than Python* |

The three detectors that are recall-limited in Python precisely because Python's
type inference is weak — `info_leakage`, `repurposed_variable`,
`pure_function_violation` — get *stronger* with the compiler path, because TS
hands you resolved types and a real symbol graph. That's the upside that turns a
"port" into an "upgrade."

**Recommendation:** a hybrid. Start on tree-sitter to land the ~15 structural
detectors cheaply and prove the facade; add an *optional* compiler-API sidecar
later for the type-aware detectors (mirrors how the AI judge is optional today —
`--ai-judge none` is fully usable). See §2 and §5/Q1.

### Decision 2 — Shared detectors vs. per-language detectors (see §1)

`PLAN.md` §11 sketches "each language gets its own `parse_*.py` and detector
adaptations." Taken literally that means **duplicating 24 detectors** — a large
drift surface. The detectors only really lean on ~10 node concepts
(`FunctionDef`, `ClassDef`, `Name`, `Attribute`, `Call`, `Assign`, `Expr`,
`Import*`, plus `walk`). So the recommended middle path is a thin
**normalized-node facade**: a uniform `FunctionLike` / `ClassLike` / `CallSite` /
`ImportEdge` interface that each language adapter populates, with detectors
written against the facade once.

This is exactly Semgrep's architecture — it maps every language's tree-sitter
CST to a common internal AST, which is what keeps it "loosely coupled with each
language." We have strong precedent that the facade approach works.

## Recommended path (lowest risk → highest value)

1. **Spike the parser decision** (§2) on 2–3 purely-structural detectors behind a
   facade. Decide tree-sitter vs. compiler-API here — cheap to learn now,
   expensive to reverse later.
2. **Land the facade + abstract the three Python-isms** in `detectors/_base.py`
   (`is_public`, `function_param_names`, `function_default_count`), then port the
   ~15 structural/import-graph detectors. The judge, reports, config, suppression
   come along unchanged.
3. **Build the TS `Project`/call-graph** (cleaner than Python given explicit
   `export`/modules) → unlocks the cross-file detectors.
4. **Defer the type-heavy + effect detectors** and the Node effects registry to
   last — same ordering logic `PLAN.md` uses for its Wave D.

## Bottom line

This is a **viable and unusually well-positioned** extension — the expensive,
judgment-heavy half (the rubric + judge) is already done and language-neutral.
The risk is concentrated and known (call-graph/module resolution), and the
worst-case detector (call-graph-dependent) has a documented external precedent
(Jelly). The recommended hybrid lets us ship value early (structural detectors on
tree-sitter) without betting the whole effort on the heavier compiler-API
integration up front.
