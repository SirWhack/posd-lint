# posd-lint

Deterministic + AI-assisted linter that surfaces violations of the principles in
John Ousterhout's *A Philosophy of Software Design*. The deterministic layer
catches the candidates; an optional Claude judge reads each candidate against
the rubric in `posd-reference.md` and decides real / borderline / false positive.

## Install (editable)

```bash
pip install -e .
```

## Quick start

```bash
# Deterministic only (no API calls)
posd-lint path/to/your/code

# Save to file
posd-lint path/to/your/code --output report.md

# JSON output (for tooling) — schema at posd_lint/data/findings.schema.json
posd-lint path/to/your/code --format json --output report.json

# With Claude judging each finding
export ANTHROPIC_API_KEY=sk-ant-...
posd-lint path/to/your/code --ai-judge claude --output report.md

# Or via Azure AI Foundry
export AZURE_FOUNDRY_API_KEY=...
export AZURE_FOUNDRY_ENDPOINT=https://...
posd-lint path/to/your/code --ai-judge claude

# Run a single detector
posd-lint path/ --detectors shallow_class,wide_interface

# Custom rubric
posd-lint path/ --rubric /path/to/your-reference.md
```

## What it detects

### Phase 1 — easy / fast

| Detector | What it flags | PoSD § |
|---|---|---|
| `vague_name` | Generic identifiers (`data`, `result`, `manager`), numbered generics (`data2`), single-letter top-level names | §13 |
| `hard_to_describe` | Public functions/methods/classes with no docstring or stub-only docstrings | §12 |
| `config_explosion` | Functions with ≥7 parameters or ≥5 optional parameters | §9 |
| `shallow_class` | Pass-through subclasses that add nothing; classes whose public methods average <4 statements each | §5 |
| `wide_interface` | Classes/Protocols with ≥12 public methods | §5 |
| `comment_repeats_code` | Comments that paraphrase the next line of code (≥60% word overlap) | §12 |

### Phase 2 — medium / heuristic

| Detector | What it flags | PoSD § |
|---|---|---|
| `pass_through_method` | A method whose body is a single forwarding call to a delegate, with no argument transformation | §8 |
| `conjoined_methods` | A private helper called by exactly one method (and not part of a dispatcher) — entanglement | §10 |
| `special_general_mixture` | Generically-named functions with ≥2 `isinstance()` checks (excludes `dispatch_*`/`parse_*`/dunders/`@singledispatch`) | §10 |
| `repurposed_variable` | A variable reassigned in a function with a different inferred kind (`list` → `dict`, `str` → `int`, etc.) | §13 |
| `impl_leaks_into_interface` | Public docstrings containing implementation phrases (`internally`, `we use`, `under the hood`, `TODO`) or private-attr references | §12 |

### Phase 3 — cross-file / heuristic

Phase 3 introduces a `Project` model built once before any detector runs (import graph, cross-file class index, attribute access map). Detectors split into two flavors: per-file `Detector` and project-level `ProjectDetector`.

| Detector | Flavor | What it flags | PoSD § |
|---|---|---|---|
| `forwarded_parameter` | per-file | A param of a small wrapper function (≤6 statements) that's only used to be passed to a downstream call | §8 |
| `required_call_ordering` | per-file | A class with paired lifecycle methods (`open`/`close`, `start`/`stop`, etc.) but no `__enter__`/`__exit__` | §6 |
| `overexposure` | project | A module exporting ≥10 public symbols where ≥3 importers each pull only ~1-2 of them | §5 |
| `temporal_decomposition` | project | ≥3 pipeline-suffixed classes (Reader/Parser/Processor/Writer/Validator/etc.) clustered in one package directory | §6 |
| `info_leakage` | project | A class whose public attributes are read directly across ≥4 external files spanning ≥3 distinct attrs — schema is leaking | §6 |

## Layout

```
posd_lint/
├── cli.py                  # entry point
├── parse.py                # AST loading, file iteration, comment extraction
├── findings.py             # Finding dataclass + verdict enum
├── detectors/              # one file per red flag
│   ├── _base.py            # ABC + registry
│   ├── vague_name.py
│   ├── hard_to_describe.py
│   ├── config_explosion.py
│   ├── shallow_class.py
│   ├── wide_interface.py
│   └── comment_repeats_code.py
├── judge/                  # AI judge layer
│   ├── claude.py           # Anthropic SDK wrapper (direct + Azure Foundry)
│   └── prompts.py          # Rubric loader + prompt construction
├── data/
│   └── posd-reference.md   # The rubric — bundled package data
└── report.py               # Markdown / JSON renderer
```

## Architecture

The deterministic layer is the **recall** mechanism — surfaces every candidate so
nothing is missed. The AI layer is the **precision** mechanism — judges each
candidate against the relevant rubric section, marks false positives, and writes
a concrete recommendation.

The two layers are orthogonal: `--ai-judge none` gives a pure static-analysis
tool; `--ai-judge claude` adds the second pass without altering the first.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

Each detector has a positive corpus file (must flag) and a negative corpus file
(must not flag). The corpus lives in `tests/corpus/`.

## Calibration notes

Thresholds were tuned against a real Python codebase (a Teams bot + Azure stack
with ~45 files). Defaults will likely need adjustment for very different
codebases — every detector accepts threshold overrides via its constructor, and
this is the right extension point if findings are too noisy or too sparse.

## What's next (phase 4 candidates)

- **Cross-frame pass-through variables.** Currently we detect intra-function forwards. Real call-graph traversal (3+ frames) would catch the fuller pattern.
- **Cycle detection in import graph.** Tight cycles between modules signal entanglement at the file level.
- **Cohesion within wide interfaces.** Once `wide_interface` flags a class, cluster its methods by parameter-type / return-type / private-attr touch and propose the split.
- **`__init__.py` re-exports vs. real exposure.** Distinguish "module re-exports a curated facade" from "module exposes everything by accident."
- **Prompt caching in the judge.** The system prompt + rubric is identical across all judge calls — a single Anthropic cache breakpoint would cut judge cost ~50% on a real run.
