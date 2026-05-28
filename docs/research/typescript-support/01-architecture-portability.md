# 01 — Architecture Portability

A layer-by-layer audit of the current codebase: what is language-neutral, what is
welded to Python's `ast`, and how to draw the seam so detectors can be shared
across languages.

## The coupling, measured

- 19 of 24 detector modules `import ast`.
- ~360 references to `ast.*` node types across detectors + `project.py` +
  `_callgraph.py`.
- The dominant node types (by frequency): `FunctionDef` (49), `AsyncFunctionDef`
  (48), `Name` (40), `ClassDef` (33), `walk` (31), `Attribute` (20), `Call` (18),
  followed by a long tail (`Assign`, `Expr`, `Constant`, `Import*`, `For`, etc.).

The important takeaway: **the detectors lean on ~10 node concepts, not the full
Python grammar.** That small surface is what makes a normalized facade feasible.

## Layer-by-layer verdict

| Layer | Files | Verdict | Notes |
|---|---|---|---|
| AI judge | `judge/claude.py`, `judge/prompts.py` | ✅ **free** | Reads excerpt + rubric section; never touches an AST. |
| Rubric | `data/posd-reference.md` | ✅ **free** | Language-universal; mentions Python twice in 454 lines. |
| Output model | `findings.py` | ✅ **free** | String-based records, no language assumptions. |
| Reporting | `report.py` | ✅ **free** | Renders `Finding`s; format-only. |
| Config | `config.py` | ✅ **free** | TOML schema; thresholds + globs. Language-neutral. |
| Suppression / baseline | `suppress.py` | 🟡 **light** | Inline-comment syntax (`# posd-lint: ignore`) needs a `//` variant. |
| CLI orchestration | `cli.py` | 🟡 **light rework** | Hard-wires `iter_python_files` / `parse_file` and a single `Project`. Needs language dispatch. |
| Parse layer | `parse.py` | 🔴 **rebuild** | `ParsedFile` wraps `ast.Module`; `.py`-only discovery; `tokenize` comments. |
| Detector base | `detectors/_base.py` | 🔴 **abstract** | 3 static helpers encode Python conventions (see below). |
| Detectors | `detectors/*.py` | 🔴 **adapt (bulk of work)** | Concepts neutral; code is Python-AST. See §3. |
| Project model | `project.py` | 🔴 **rebuild** | Cross-file indexes built on `ast` + Python module system. |
| Call graph | `_callgraph.py` | 🔴 **rebuild (hardest)** | Resolution depends on `import`/`from` semantics + dynamic typing. |
| Effects | `effects.py` + `data/effects.toml` | 🟡 algorithm free, registry rebuild | Tarjan SCC is language-agnostic; the symbol registry is Python/stdlib-specific. |

## The three Python-isms in `detectors/_base.py`

These static helpers are inherited by every per-file detector and bake in Python
conventions. They are the first thing to abstract:

- `is_public(name)` — leading-underscore convention. **TS:** `private`/`protected`
  keywords, `#private` fields, and `export` (module-level visibility). A name with
  no leading underscore is not necessarily "public" in TS — non-exported is
  module-private regardless of name.
- `function_param_names(node)` — pulls `posonlyargs + args + kwonlyargs`, filters
  `self`/`cls`. **TS:** no positional-only/keyword-only split; no `self`/`cls`;
  destructured params and `this` parameter are the wrinkles.
- `function_default_count(node)` — sums positional + keyword-only defaults. **TS:**
  defaults are simpler (`x = 5`), but optional params (`x?:`) are a second axis
  that has no Python analog.

**Recommendation:** lift these onto the language adapter, not the detector base.
Each language reports "public surface", "parameters", "optional/required" through
the facade; detectors consume those abstractions.

## The recommended seam: a normalized-node facade

Rather than have detectors switch on `ast.ClassDef` vs. a tree-sitter
`class_declaration` node, introduce a thin uniform model that each language
adapter populates. The facade only needs to cover the ~10 concepts the detectors
actually use:

```
FunctionLike   name, params[], is_public, is_async, body_stmt_count,
               docstring/jsdoc, decorators[], enclosing_class, span
ClassLike      name, bases/implements[], methods[], attributes[],
               decorators[], is_exported, span
CallSite       callee (resolved qualname | None), args[], receiver, span
NameRef        identifier, span (read/write)
ImportEdge     source_module, imported_symbols[], alias, span
Comment        text, span, kind (line/block/doc)
ModuleSurface  exported_symbols[], file_path
```

Detectors are written once against this facade. Language adapters
(`lang/python/adapter.py`, `lang/typescript/adapter.py`) translate their native
tree into facade nodes.

### Precedent: this is how Semgrep does it

Semgrep parses each language with tree-sitter to a concrete syntax tree, then
**maps every language's CST onto a single common "Semgrep AST."** Per their own
description, this is what keeps the engine "loosely coupled with each language"
and "highly extensible." We are proposing the same shape, scoped to the ~10
concepts our detectors need rather than a general-purpose IR.

### Where the facade is leaky (and that's OK)

Some detectors are intrinsically Python-flavored and won't have a TS counterpart
through the facade — e.g. `required_call_ordering` keys off the context-manager
protocol (`__enter__`/`__exit__`), which has no direct TS equivalent (the nearest
is `using` + `Symbol.dispose`, TS 5.2+). The facade should allow a detector to
declare which languages it applies to, and the registry should skip
non-applicable detectors per language rather than force a meaningless mapping.

## What gets *easier* in TypeScript

TypeScript is not uniformly harder — several things are cleaner than Python:

- **Visibility is explicit.** `export`, `private`, `protected`, `#field` remove
  the guesswork in `is_public`, `overexposure`, `info_leakage`, `unstable_interface`.
- **Interfaces are first-class.** `wide_interface` and `unstable_interface` map
  directly onto `interface` declarations instead of inferring "interface-ness."
- **The module graph is explicit.** `export`/`import` with real module resolution
  is more tractable than Python's `__init__.py` + dotted-name guessing — *if* we
  use a resolver that understands `tsconfig.json` paths.
- **Static types exist.** The detectors that approximate types in Python
  (`info_leakage`, `repurposed_variable`) can consume real types — see §2.

## What stays hard

- **Call graph** (`_callgraph.py`). Python resolution leans on `self.foo()`,
  typed-local `obj.foo()`, `module.foo()` via import aliases, and bare top-level
  calls. The TS analog needs either (a) tree-sitter heuristics (approximate, like
  today) or (b) the compiler's symbol resolver (accurate). The two cross-file
  detectors that depend on it (`import_cycle` indirectly via module graph,
  `pass_through_variable` directly) are the hard ports.
- **Module path resolution.** No `__init__.py`; instead `index.ts`, path
  aliases, `baseUrl`, `paths`, `.d.ts`, re-exports (`export * from`). A correct
  resolver effectively means reading `tsconfig.json`.

## Summary

The architecture is well-suited to multi-language: the judgment-heavy half is
already neutral, and the detector surface touches a small, abstractable set of
node concepts. The realistic plan is **facade + per-language adapter**, not 24
duplicated detectors, with the call-graph/module-resolution subsystem as the
acknowledged hard core.
