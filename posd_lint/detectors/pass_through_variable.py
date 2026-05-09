"""Cross-function pass-through parameters (PoSD §8).

The intra-function form (`forwarded_parameter`) flags a param that's threaded
through one wrapper into a call. This detector handles the harder case:
a parameter forwarded unchanged through ≥2 frames before any frame reads it.

    def outer(x):       # `x` is irrelevant to outer
        return middle(x)

    def middle(x):      # `x` is irrelevant to middle
        return leaf(x)

    def leaf(x):        # only here is `x` actually used
        return x.upper()

That's a textbook pass-through variable: middle layers know about something
they have no business knowing about. We flag `outer` (the entry point of the
chain) so the user sees the smell at the top, where they'd refactor it.

Detection shape (project-level):
- Per function, index its params, the calls it makes (resolved via
  `Project.call_sites`), which call args are pass-throughs of which param
  (positional or by name), and which params are *read* outside of forwarding.
- Walk: param `x` of caller is pass-through iff it's forwarded unchanged into
  a callee, the callee is itself a pass-through-or-leaf for that param slot,
  and the chain length is ≥2 frames before the read (so single-hop wrappers
  remain the territory of `forwarded_parameter`).

Calibration knobs:
- MAX_DEPTH bounds graph descent so cyclic call graphs terminate quickly.
- A param that's read by *any* frame in the chain (even if also forwarded)
  is not a pass-through — the middle frame has a legitimate use for it.
"""

from __future__ import annotations

import ast
from typing import Iterable, Optional

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project


MAX_DEPTH = 3            # outer -> middle -> leaf is depth 2; allow one more frame
MIN_FRAMES_BEFORE_READ = 2  # the param must be forwarded through ≥2 frames before reaching a read


@register_project
class PassThroughVariableDetector(ProjectDetector):
    name = "pass_through_variable"
    title = "Pass-through variable"
    rubric_ref = "8"
    rubric_title = "Different layer, different abstraction"

    def detect_project(self, project: Project) -> Iterable[Finding]:
        index = _build_function_index(project)
        if not index:
            return

        for qual, info in index.items():
            if _should_skip(info.node):
                continue
            for param in info.params:
                if param in info.read_params:
                    continue
                forwarding = info.forwarding.get(param, [])
                if not forwarding:
                    continue
                chain = _trace_chain(qual, param, index, depth=1, visited=set())
                if chain is None:
                    continue
                if len(chain) < MIN_FRAMES_BEFORE_READ:
                    continue
                yield Finding(
                    file=info.file_path,
                    line=info.node.lineno,
                    detector=self.name,
                    title=f"Parameter '{param}' of '{info.node.name}' is a pass-through variable",
                    evidence=(
                        f"forwarded through {len(chain)} frames before being read: "
                        + " -> ".join(chain)
                    ),
                    rubric_ref=self.rubric_ref,
                    rubric_title=self.rubric_title,
                    severity=Severity.LOW,
                    code_excerpt=_excerpt(project, info),
                )


class _FuncInfo:
    """Pre-computed analysis of one function relevant to pass-through detection."""

    __slots__ = ("qualname", "node", "file_path", "params", "param_index",
                 "read_params", "forwarding")

    def __init__(
        self,
        qualname: str,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        params: list[str],
    ) -> None:
        self.qualname = qualname
        self.node = node
        self.file_path = file_path
        self.params = params
        self.param_index = {name: i for i, name in enumerate(params)}
        # param_name -> True if read in any way other than as a forwarded call arg
        self.read_params: set[str] = set()
        # param_name -> list of (callee_qualname, position_in_callee) edges
        self.forwarding: dict[str, list[tuple[str, int]]] = {}


def _build_function_index(project: Project) -> dict[str, _FuncInfo]:
    """Index every function we can resolve — params, reads, and forwarding edges."""
    qualname_to_info: dict[str, _FuncInfo] = {}

    # First pass: collect every function with its params (drop self/cls so
    # positions we record line up with what calls actually pass).
    for site in project.call_sites:
        if site.caller_qualname in qualname_to_info:
            continue
        params = _func_params(site.func_node)
        qualname_to_info[site.caller_qualname] = _FuncInfo(
            qualname=site.caller_qualname,
            node=site.func_node,
            file_path=site.file_path,
            params=params,
        )

    # Some functions never call anything — they won't appear in call_sites.
    # Add them too: they're terminal leaves where reads are detected.
    seen_files: set[str] = set()
    for site in project.call_sites:
        seen_files.add(site.file_path)
    for f in project.files:
        module_qual = project._qualname_for(f.path)
        for fn_node, qual in _iter_functions_with_qualnames(f.tree, module_qual):
            if qual in qualname_to_info:
                continue
            qualname_to_info[qual] = _FuncInfo(
                qualname=qual,
                node=fn_node,
                file_path=f.path,
                params=_func_params(fn_node),
            )

    # Second pass: classify every Name read of each param as either "forwarded
    # at a known call site" or "read elsewhere".
    forwarded_reads_by_func: dict[str, set[int]] = {qual: set() for qual in qualname_to_info}
    for site in project.call_sites:
        info = qualname_to_info.get(site.caller_qualname)
        if info is None:
            continue
        callee_info = qualname_to_info.get(site.callee_qualname)
        if callee_info is None:
            continue
        for pos, arg in enumerate(site.call.args):
            param = _arg_passes_param(arg, info.params)
            if param is None:
                continue
            if pos >= len(callee_info.params):
                continue  # *args spread or position out of range
            forwarded_reads_by_func[info.qualname].add(id(arg))
            info.forwarding.setdefault(param, []).append(
                (site.callee_qualname, pos)
            )
        for kw in site.call.keywords:
            if kw.arg is None:
                continue
            param = _arg_passes_param(kw.value, info.params)
            if param is None:
                continue
            if kw.arg not in callee_info.param_index:
                continue
            forwarded_reads_by_func[info.qualname].add(id(kw.value))
            info.forwarding.setdefault(param, []).append(
                (site.callee_qualname, callee_info.param_index[kw.arg])
            )

    # Third pass: any Name(Load) of a param that isn't one of the recorded
    # forwarding reads counts as a "real" read.
    for info in qualname_to_info.values():
        forwarded_ids = forwarded_reads_by_func.get(info.qualname, set())
        for sub in ast.walk(info.node):
            if not isinstance(sub, ast.Name):
                continue
            if sub.id not in info.param_index:
                continue
            if not isinstance(sub.ctx, ast.Load):
                continue
            if id(sub) in forwarded_ids:
                continue
            info.read_params.add(sub.id)

    return qualname_to_info


def _trace_chain(
    qualname: str,
    param: str,
    index: dict[str, _FuncInfo],
    depth: int,
    visited: set[tuple[str, str]],
) -> Optional[list[str]]:
    """Return the chain of function names where `param` is forwarded unread,
    ending at the function that finally reads it. None if no such chain.

    The returned list represents the *frames between the start and the read*:
    e.g. for outer -> middle -> leaf it returns ['middle', 'leaf']. The
    caller checks len(chain) >= MIN_FRAMES_BEFORE_READ.
    """
    if depth > MAX_DEPTH:
        return None
    key = (qualname, param)
    if key in visited:
        return None
    visited = visited | {key}

    info = index.get(qualname)
    if info is None:
        return None
    edges = info.forwarding.get(param, [])
    for callee_qual, pos in edges:
        callee = index.get(callee_qual)
        if callee is None:
            continue
        if pos >= len(callee.params):
            continue
        callee_param = callee.params[pos]
        callee_name = callee.node.name
        if callee_param in callee.read_params:
            return [callee_name]
        deeper = _trace_chain(callee_qual, callee_param, index, depth + 1, visited)
        if deeper is not None:
            return [callee_name] + deeper
    return None


def _func_params(node: ast.AST) -> list[str]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    args = node.args
    names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
    return [n for n in names if n not in ("self", "cls")]


def _arg_passes_param(arg: ast.AST, params: list[str]) -> Optional[str]:
    """If arg is a bare Name reference to one of `params`, return its name.

    Anything wrapped (`x.upper()`, `x + 1`, `f(x)`) doesn't count — that's a
    transform, and the param has been used.
    """
    if isinstance(arg, ast.Name) and arg.id in params:
        return arg.id
    return None


def _iter_functions_with_qualnames(tree: ast.Module, module_qual: str):
    """Yield (FunctionDef, qualname) for every top-level and nested-in-class function."""
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = f"{module_qual}.{stmt.name}" if module_qual else stmt.name
            yield stmt, qual
        elif isinstance(stmt, ast.ClassDef):
            for item in stmt.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    parts = [p for p in (module_qual, stmt.name, item.name) if p]
                    yield item, ".".join(parts)


def _should_skip(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if node.name.startswith("__") and node.name.endswith("__"):
        return True
    # **kwargs forwarding is a recognized idiom (decorators, factories) — too
    # noisy to treat as a smell.
    if node.args.kwarg is not None:
        return True
    return False


def _excerpt(project: Project, info: _FuncInfo) -> str:
    for f in project.files:
        if f.path == info.file_path:
            end = info.node.lineno + 3
            return f.excerpt(info.node.lineno, end, context=1)
    return ""
