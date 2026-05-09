"""Effect tracking — which functions have side-effects (PoSD §13).

Two layers:

1. A static curated registry (`data/effects.toml`) maps fully-qualified symbol
   names to effect categories: filesystem, network, database, global_state,
   subprocess, stdout, time, random. Anything not in the registry is treated
   as pure-by-default.

2. Propagation through the project's call graph. A function's effect set is
   its direct effects ∪ the effects of every function it calls. We use a
   Tarjan-style SCC contraction so cyclic call graphs converge.

The matcher is permissive: a call to `requests.get` and a call to
`requests.Session.get` both bind to the same `network` effect, and a call to
`open(...)` matches `builtins.open` even though no `builtins` import was
written. Recall over precision — the registry decides, and any candidate
dotted form a call could plausibly mean is checked against it.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Iterable

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


_DEFAULT_EFFECTS_PATH = Path(__file__).parent / "data" / "effects.toml"


@lru_cache(maxsize=1)
def load_effect_registry() -> dict[str, str]:
    """Read effects.toml and return {fully_qualified_symbol: effect_category}.

    Cached for the process — the registry is static and reading it on every
    call would dominate the cost of effect computation.
    """
    try:
        with resources.files("posd_lint.data").joinpath("effects.toml").open("rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, ModuleNotFoundError):
        with _DEFAULT_EFFECTS_PATH.open("rb") as fh:
            data = tomllib.load(fh)

    out: dict[str, str] = {}
    for category, body in data.items():
        for symbol in body.get("symbols", []):
            out[symbol] = category
    return out


def match_effect(candidates: Iterable[str], registry: dict[str, str]) -> str | None:
    """Return the effect category for the first candidate that hits the registry.

    Candidates come from `_callgraph.build_external_calls`; they're ordered
    most-specific first (`pathlib.Path.read_text`) to least-specific
    (`read_text`). The least-specific tail catches cases where the receiver
    is unknown but the method name is unique enough to be diagnostic.
    """
    for cand in candidates:
        if cand in registry:
            return registry[cand]
        # Permissive: try last-two-segment suffix for `module.ClassName.method`.
        parts = cand.split(".")
        if len(parts) >= 2:
            tail = ".".join(parts[-2:])
            if tail in registry:
                return registry[tail]
    return None


def compute_function_effects(
    call_graph: dict[str, set[str]],
    external_calls: dict[str, set[str]],
    registry: dict[str, str] | None = None,
    all_functions: Iterable[str] = (),
) -> dict[str, set[str]]:
    """Propagate effects through the call graph.

    Direct effects: for each function, every external call's effect category.
    Transitive: walk call_graph; a function inherits the effects of every
    function it (transitively) calls. Cycles are handled by contracting
    each SCC into a single node before propagation, which guarantees a
    fixed point in one pass.
    """
    if registry is None:
        registry = load_effect_registry()

    # Direct effects per function.
    direct: dict[str, set[str]] = defaultdict(set)
    for caller, externs in external_calls.items():
        for ext in externs:
            effect = match_effect([ext], registry)
            if effect is not None:
                direct[caller].add(effect)

    # Make sure every node in the call graph has an entry (even if empty).
    nodes: set[str] = set(call_graph.keys()) | set(direct.keys()) | set(all_functions)
    for callees in call_graph.values():
        nodes.update(callees)

    # Tarjan SCC over the call graph (reverse-topological order is the natural
    # output, which is exactly what we want for forward-effect propagation:
    # callees first, then callers).
    sccs = _tarjan_scc({n: call_graph.get(n, set()) for n in nodes})
    node_to_scc: dict[str, int] = {}
    for i, comp in enumerate(sccs):
        for n in comp:
            node_to_scc[n] = i

    scc_effects: list[set[str]] = [set() for _ in sccs]
    for i, comp in enumerate(sccs):
        for n in comp:
            scc_effects[i].update(direct.get(n, set()))

    # SCC-graph edges (callee SCC -> caller SCC propagation).
    scc_callees: list[set[int]] = [set() for _ in sccs]
    for caller, callees in call_graph.items():
        i = node_to_scc[caller]
        for callee in callees:
            j = node_to_scc.get(callee)
            if j is None or j == i:
                continue
            scc_callees[i].add(j)

    # Propagate in reverse-topological order. Tarjan emits SCCs in
    # reverse-topological order (leaves first), so iterating in order means
    # every callee SCC is fully resolved before its caller SCC consumes it.
    for i in range(len(sccs)):
        for j in scc_callees[i]:
            scc_effects[i].update(scc_effects[j])

    out: dict[str, set[str]] = {}
    for n in nodes:
        i = node_to_scc[n]
        if scc_effects[i]:
            out[n] = set(scc_effects[i])
        else:
            out[n] = set()
    return out


def _tarjan_scc(graph: dict[str, set[str]]) -> list[list[str]]:
    """Iterative Tarjan SCC — emits SCCs in reverse-topological order.

    Same shape as the helper in detectors/import_cycle.py but kept local so
    this module has zero detector dependencies (effects.py is upstream of
    every detector that uses it).
    """
    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = 0

    for start in graph:
        if start in index_of:
            continue
        work: list[tuple[str, list[str], int]] = [
            (start, sorted(graph.get(start, set())), 0)
        ]
        index_of[start] = counter
        lowlink[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)

        while work:
            node, succs, pos = work[-1]
            if pos >= len(succs):
                if lowlink[node] == index_of[node]:
                    component: list[str] = []
                    while True:
                        popped = stack.pop()
                        on_stack.discard(popped)
                        component.append(popped)
                        if popped == node:
                            break
                    sccs.append(component)
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                continue

            next_succ = succs[pos]
            work[-1] = (node, succs, pos + 1)

            if next_succ not in index_of:
                index_of[next_succ] = counter
                lowlink[next_succ] = counter
                counter += 1
                stack.append(next_succ)
                on_stack.add(next_succ)
                work.append((next_succ, sorted(graph.get(next_succ, set())), 0))
            elif next_succ in on_stack:
                lowlink[node] = min(lowlink[node], index_of[next_succ])

    return sccs
