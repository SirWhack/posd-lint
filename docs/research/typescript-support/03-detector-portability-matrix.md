# 03 — Detector Portability Matrix

All 24 detectors, classified by how cleanly the underlying *concept* maps to
TypeScript and what specific adaptation each needs. Derived from a full read of
every detector module plus `_base.py`, `project.py`, `_callgraph.py`, and
`effects.py`.

## Legend

- **Clean** — concept maps directly; adaptation is mechanical (swap node types via
  the facade, adjust naming conventions).
- **Better** — TypeScript's explicit `export`/`interface`/types make the detector
  *more accurate* than its Python version.
- **Adapt** — concept is language-neutral but the mechanics need real rework
  (docstrings→JSDoc, `isinstance`→`instanceof`, `_priv`→`private`, etc.).
- **Hard** — depends on the call-graph/module-resolution subsystem; gated on §2.
- **N/A-ish** — concept is Python-idiom-bound; needs reframing or may not apply.

## Per-file detectors (15)

| Detector | §  | Concept (language-neutral) | Verdict | Adaptation needed |
|---|---|---|---|---|
| `vague_name` | 13 | Generic/uninformative identifiers; "couldn't pick a name" tells (`_v2`, `_new`) | **Clean** | Drop `self`/`cls` handling; keep version-suffix patterns; consider camelCase vs snake_case generics. |
| `hard_to_describe` | 12 | Public API with no/stub contract documentation | **Adapt** | Python docstring (first `Expr`/`Constant`) → JSDoc `/** */` preceding the decl. No dunders to skip. |
| `config_explosion` | 9 | Too many parameters / too many optional parameters | **Clean** | No posonly/kwonly split; optional is `x?:` and defaults `x=`. Thresholds unchanged. |
| `shallow_class` | 5 | Class interface wide relative to functionality it hides; pass-through subclass | **Clean** | Exempt-decorator list (`@dataclass`) → TS equivalents (or drop); base-class exemptions → TS (`Error`, enums). Body-statement counting maps. |
| `wide_interface` | 5 | Too many public methods on a class/interface | **Better** | TS `interface` is a first-class target; `export`+visibility makes "public" exact. Drop dunder exclusion. |
| `comment_repeats_code` | 12 | Comment restates the next line of code | **Clean** | `//` and `/* */` instead of `#`. Tree-sitter keeps comments in the CST → simpler than Python's `tokenize` pass. Jaccard logic unchanged. |
| `pass_through_method` | 8 | Method just forwards 1:1 to another call, adding nothing | **Clean** | `this.` instead of `self.`; single-statement body shape match is identical. |
| `conjoined_methods` | 10 | Private helper used by exactly one method; can't understand one without the other | **Adapt** | "Private" via `private`/`#`/non-export instead of `_` prefix. Dispatcher exemption logic unchanged. |
| `special_general_mixture` | 10 | Type-branching inside a general-purpose function | **Adapt** | `isinstance(x, T)` → `x instanceof T` / `typeof` / discriminated-union `switch`. Threshold + dispatch-name exemptions carry. |
| `repurposed_variable` | 13 | One variable reused for semantically different values | **Better** | Heuristic kind-inference → real types (Option B) or `let` reassignment with changed literal kind (Option A). `const` can't reassign — useful signal. |
| `impl_leaks_into_interface` | 12 | Implementation detail bleeds into public-facing docs | **Adapt** | Leak-phrase regex carries; docstring source → JSDoc; `self._x` reference → `this.#x`/`private`. |
| `forwarded_parameter` | 8 | Wrapper param used only to forward into one call | **Clean** | Param read-counting maps directly. |
| `required_call_ordering` | 6 | Paired lifecycle methods (open/close…) with no scoped-resource construct | **N/A-ish** | Python keys off missing `__enter__`/`__exit__`. TS analog is `using`/`Symbol.dispose` (TS 5.2+) or `try/finally`. Reframe or scope to TS idioms; lowest-priority port. |
| `duplicate_code` | 10 | Repeated logic (normalized-AST hash, ignoring local names) | **Adapt** | Re-implement the AST normalizer for the TS tree (account for `const`/`let`, type annotations, async). Concept identical. |
| `cyclomatic_complexity` | 17 | Non-obvious code via branch density | **Clean** | Count `if`/`for`/`while`/`catch`/`&&`/`||`/`?:`/`case`. No comprehensions; ternaries and `??` are the new contributors. |

## Project-level detectors (9)

| Detector | §  | Concept | Verdict | Adaptation needed |
|---|---|---|---|---|
| `overexposure` | 5 | Module exports many symbols, each importer uses few | **Better** | TS `export` is explicit → exposed-surface count is exact, not inferred. Needs import-graph (Option A heuristic or B resolver). |
| `temporal_decomposition` | 6 | Cluster of pipeline-suffixed classes (Reader/Writer/Parser…) in one dir | **Clean** | Pure class-name pattern over the class index; suffix list unchanged. |
| `info_leakage` | 6 | One class's internals read across many external files | **Better (with B)** | Cross-file attribute reads with receiver typing. Option A: approximate (≈ today). Option B: resolved types → near-complete recall (fixes G3). |
| `import_cycle` | 6 | Circular module dependencies (Tarjan SCC) | **Hard** | Tarjan is language-agnostic; the input (module graph) needs a TS resolver honoring `tsconfig` paths/re-exports. |
| `pass_through_variable` | 8 | Data threaded unchanged through ≥2 call frames | **Hard** | Directly depends on the call graph; best with Option B's symbol resolution. The single hardest port. |
| `forbidden_import` | 6 | Config-declared module bans by path glob | **Clean** | Glob + config logic unchanged; only import extraction differs. |
| `boundary_violation` | 6/8 | Layer X imports a layer it isn't allowed to | **Clean** | Same as above; layer globs + allowed-imports config carry verbatim. |
| `unstable_interface` | 5 | High-fan-in concrete class with no interface/ABC boundary | **Better** | TS `interface`/`implements` is explicit → check "does this class implement an interface" precisely instead of ABC/Protocol heuristics. |
| `pure_function_violation` | 13 | Function named as pure (`calculate_`, `to_`…) but has effects | **Adapt + Hard** | Name-prefix detection is trivial; effect attribution needs (a) a new **Node/browser/npm effects registry** to replace `effects.toml` and (b) the call graph. |

## Roll-up

- **Clean / Better:** ~18 of 24 — the structural and import-graph detectors, with
  several *improving* in TS thanks to explicit `export`/`interface`/types.
- **Adapt:** the docstring-, isinstance-, and privacy-flavored detectors plus the
  duplicate-code normalizer — real work, but bounded and per-detector.
- **Hard:** `import_cycle`, `pass_through_variable`, and the effect side of
  `pure_function_violation` — all gated on the call-graph/module-resolution
  subsystem and therefore on the §2 parser decision.
- **N/A-ish:** `required_call_ordering` — Python-idiom-bound; reframe to TS
  scoped-resource constructs or deprioritize.

## Cross-cutting adaptations (do once, not per detector)

These belong in the language adapter / facade, and most of the per-detector
"adapt" notes above collapse into them:

1. **Visibility model** — `export` + `private`/`protected`/`#` replaces
   leading-underscore. Powers `is_public` for every detector at once.
2. **Doc-comment model** — JSDoc extraction replaces docstring extraction. Powers
   `hard_to_describe`, `impl_leaks_into_interface`.
3. **Parameter model** — required/optional/default/destructured/rest, no
   `self`/`cls`. Powers `config_explosion`, `forwarded_parameter`.
4. **Type model** — present (Option B) or absent (Option A). Powers `info_leakage`,
   `repurposed_variable`, `pure_function_violation`.
5. **Import/module model** — explicit `export`/`import` with a `tsconfig`-aware
   resolver. Powers every project-level detector.
6. **Effects registry** — a TS/Node/npm `effects.toml` sibling. The Tarjan
   propagation in `effects.py` is reused as-is.
