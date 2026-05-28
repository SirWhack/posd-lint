# 02 — Parser & Tooling Options

This is the decision that most shapes the result. It determines how good
TypeScript support can be, what runtime dependencies we take on, and which
detectors are reachable.

## The fork

To analyze TypeScript from a Python tool, the source has to become a tree we can
walk. There are two fundamentally different sources for that tree, distinguished
by **whether they carry resolved type information.**

### Option A — Tree-sitter (syntax only)

[`py-tree-sitter`](https://github.com/tree-sitter/py-tree-sitter) provides Python
bindings to the tree-sitter parsing library, with the
[`tree-sitter-typescript`](https://github.com/tree-sitter/tree-sitter-typescript)
grammar (MIT). It is actively maintained (0.25.x as of late 2025), ships
pre-compiled wheels with no library dependencies, and exposes a query system with
predicates for pattern matching.

- **What you get:** a concrete syntax tree. Functions, classes, params, calls,
  imports, comments, spans — everything structural.
- **What you don't get:** *types*. Tree-sitter does not resolve symbols or know
  that `const u = getUser()` makes `u` a `User`. It's a parser, not a type
  checker. (It's the tooling behind editor syntax highlighting and ast-grep.)
- **Cost:** essentially free. Pure-Python install, very fast, no Node.js.

### Option B — TypeScript compiler API (full types), via a Node sidecar

The TypeScript compiler exposes a type checker:
`program.getTypeChecker()`, with `getSymbolAtLocation`, `getTypeAtLocation`,
`getTypeOfSymbolAtLocation`, `typeToString`, etc.
[`ts-morph`](https://github.com/dsherret/ts-morph) is the ergonomic wrapper most
analysis tools build on — it gives "full access to TypeScript type information"
and integrates the type checker for precise symbol/type retrieval.

- **What you get:** resolved types, a real symbol graph, accurate cross-file
  resolution that honors `tsconfig.json` (`paths`, `baseUrl`, re-exports).
- **Cost:** it's a **Node.js library** — Python can't call it in-process. We'd run
  a Node sidecar (subprocess) that parses + type-checks and emits a JSON facade
  over IPC/stdout, which the Python side consumes. Adds a Node toolchain
  dependency and IPC complexity, and type-checking a whole program is slower than
  parsing.

## Why the type fork matters: three detectors flip from "port" to "upgrade"

`PLAN.md` already records that Python's receiver type-inference is the weak point
(gap **G3**) limiting `info_leakage` recall, and that `repurposed_variable` /
`pure_function_violation` lean on heuristic type/effect inference. In TypeScript,
the compiler hands you what Python had to guess:

| Detector | In Python today | With TS compiler API |
|---|---|---|
| `info_leakage` | recall-limited; receiver type inference only covers annotated params + constructor assignments (G3) | resolved types on every attribute access → near-complete recall |
| `repurposed_variable` | infers "kind" from literal shapes (`[]`→list, `""`→str) | the declared/narrowed type is known exactly |
| `pure_function_violation` | depends on an approximate call graph + curated effect registry | accurate symbol resolution sharpens both call graph and effect attribution |

With tree-sitter alone these three remain approximate (about as good as the
current Python versions). With the compiler API they become *better than the
Python originals*. That is the strategic upside of Option B.

## How comparable tools chose

- **Semgrep** uses **tree-sitter** to get a CST per language, then maps it to a
  common internal AST; it layers "limited dataflow" on top rather than relying on
  a per-language type checker. Breadth-first, syntax-led.
- **ast-grep** is tree-sitter-based, structural search/lint/rewrite across many
  languages. Syntax-led.
- **Jelly** ([cs-au-dk/jelly](https://github.com/cs-au-dk/jelly)) is a dedicated
  JS/TS static analyzer for **call-graph construction** and library-usage
  analysis, built on flow-insensitive points-to analysis. Relevant precedent that
  TS call graphs are a solved-but-nontrivial problem — and a possible reference
  (or even a component) for our hard cross-file detectors.
- **ESLint / typescript-eslint** are the in-ecosystem standard and *do* offer
  type-aware rules — by running inside the Node/TS toolchain. That's the world
  Option B buys into.

The pattern: tools that want **breadth and portability** pick tree-sitter and a
common AST; tools that want **type-aware precision** pay for the compiler. Our
codebase wants both at different times — hence the hybrid.

## Recommendation: hybrid, tree-sitter first

Mirror the existing `--ai-judge none` philosophy (the tool is fully usable
without the heavy/optional dependency):

1. **Phase 1 — tree-sitter only.** Lands the ~15 structural detectors and the
   import-graph detectors. Pure-Python, fast, no Node. Proves the facade. This is
   a complete, shippable TS mode on its own.
2. **Phase 2 — optional compiler-API sidecar.** Add a `--ts-types` (working name)
   mode that spins up the Node/`ts-morph` sidecar to enrich the facade with
   resolved types and an accurate symbol graph. Unlocks/upgrades the three
   type-hungry detectors and sharpens the call graph. Degrades gracefully to
   tree-sitter-only when Node isn't present — exactly like the judge degrades
   without API creds.

This sequencing de-risks the project: we ship value before betting on the
heavier integration, and the facade boundary (§1) is what lets the same detectors
run against either an enriched or a syntax-only tree.

## Practical notes / gotchas

- **Comments.** Tree-sitter keeps comments in the CST (Semgrep deliberately drops
  them; we *need* them for `comment_repeats_code`). So tree-sitter actually
  simplifies our comment story vs. Python's separate `tokenize` pass.
- **JS vs TS vs TSX.** `tree-sitter-typescript` ships separate `typescript` and
  `tsx` grammars; JS is a near-subset. File-extension dispatch
  (`.ts/.tsx/.mts/.cts/.js/.jsx`) belongs in the adapter.
- **Sidecar packaging.** If we go Option B, decide whether Node is a hard
  prerequisite for `--ts-types` or whether we vendor a pinned sidecar. Likely:
  document Node as a prerequisite for the type-aware mode only (extras-style),
  keep tree-sitter mode dependency-light.
- **Performance.** Tree-sitter is fast enough to be unremarkable. The compiler API
  type-checks the whole program once (`ts.createProgram`), which is the slow step
  — amortized across all files, acceptable for a lint pass, but not free.

## Sources

- [tree-sitter/py-tree-sitter](https://github.com/tree-sitter/py-tree-sitter)
- [py-tree-sitter docs](https://tree-sitter.github.io/py-tree-sitter/)
- [tree-sitter/tree-sitter-typescript](https://github.com/tree-sitter/tree-sitter-typescript)
- [dsherret/ts-morph](https://github.com/dsherret/ts-morph) · [ts-morph docs](https://ts-morph.com/)
- [Using the TypeScript Compiler API (microsoft/TypeScript wiki)](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API)
- [semgrep/semgrep](https://github.com/semgrep/semgrep) · [semgrep-core contributing](https://semgrep.dev/docs/contributing/semgrep-core-contributing)
- [ast-grep (Hacker News discussion)](https://news.ycombinator.com/item?id=38590984)
- [cs-au-dk/jelly](https://github.com/cs-au-dk/jelly)
