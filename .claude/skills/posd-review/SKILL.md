---
name: posd-review
description: Run posd-lint against the current codebase or a specified path and present an inline summary of PoSD red flags. Use when the user asks to "review code with posd-lint", "run posd lint", "posd review", or wants a Philosophy of Software Design audit of their code.
allowed-tools: Bash, Read
---

# posd-review

Run [posd-lint](https://github.com/) — a deterministic + AI-assisted linter for John Ousterhout's *A Philosophy of Software Design* — against the user's code, then surface the most important findings inline.

## When to invoke

- "review code with posd-lint"
- "run posd lint"
- "posd review"
- "audit this for PoSD violations"
- "check for shallow modules / wide interfaces / etc."

## Steps

1. **Determine the target path.**
   - If the user supplied a path, use it.
   - Else if the current working directory is inside a git working tree, use the repo root (`git rev-parse --show-toplevel`).
   - Else use `.`.

2. **Decide whether to run the AI judge.**
   - Default: `--ai-judge claude` (precision pass; needs `ANTHROPIC_API_KEY` or Azure Foundry env).
   - If the user opts out, says "fast", "no AI", or no API key is set, use `--ai-judge none`.

3. **Run posd-lint.** From the posd-lint repo (or wherever it's installed):

   ```bash
   python3 -m posd_lint.cli <target> --ai-judge claude --output /tmp/posd-review.md
   ```

   For machine-readable output (e.g. to filter or count programmatically):

   ```bash
   python3 -m posd_lint.cli <target> --ai-judge none --format json --output /tmp/posd-review.json
   ```

   The JSON output conforms to `posd_lint/data/findings.schema.json`.

4. **Read `/tmp/posd-review.md`** and present:
   - The summary table verbatim (per-detector counts + verdicts).
   - The top 3–5 highest-severity findings, each with: file:line, detector, evidence, and the judge's recommendation if present.
   - A one-line pointer to the full report at `/tmp/posd-review.md`.

## Notes

- Detectors carry a `rubric_ref` (e.g. `"5"`) that maps to the matching `## 5. Deep vs. shallow modules` section in `posd-reference.md`. When citing a finding, mention the rubric section so the user can read the framing.
- False positives are dropped from the markdown report by default but kept in the JSON. Use the JSON if the user wants to audit the judge.
- Do not edit the user's code without being asked. This skill reports; it does not refactor.
