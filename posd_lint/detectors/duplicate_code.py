"""Duplicated function bodies (PoSD §10 — Better together or better apart).

Two functions whose bodies have the same shape — same control flow, same
operator types, same call structure — almost always mean an abstraction was
missed. The bodies were copy-pasted and the names tweaked. Folding them
together into one parameterised function (or a shared helper) is the §10
'combine when there is duplication' move.

Detection shape:
- For each function/method, compute a normalized AST signature:
  - Walk in deterministic order; record (type_name, child_count) per node.
  - Replace local variable / parameter names with positional placeholders
    (`_v0`, `_v1`, ...) so renamed-but-identical bodies hash to the same value.
  - Strip docstrings.
  - Operator types (BinOp.op type, Compare ops, BoolOp.op type) ARE part of
    the signature, so `x + y` and `x * y` don't collide.
- Group functions in the same file by signature.
- Flag groups of size ≥2; emit one finding per group, anchored at the first
  function, with the others listed in evidence.
- Skip trivial functions (≤3 statements walked) — boilerplate stubs and
  one-liners are not interesting duplicates.
"""

from __future__ import annotations

import ast
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile


MIN_BODY_STATEMENTS = 4  # ≤3 walked stmts → trivial; not worth flagging


@register
class DuplicateCodeDetector(Detector):
    name = "duplicate_code"
    title = "Duplicated function bodies"
    rubric_ref = "10"
    rubric_title = "Better together or better apart"

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        groups: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        for node in ast.walk(file.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _walked_statement_count(node) < MIN_BODY_STATEMENTS:
                continue
            signature = _normalized_signature(node)
            groups.setdefault(signature, []).append(node)

        for fns in groups.values():
            if len(fns) < 2:
                continue
            fns.sort(key=lambda f: f.lineno)
            anchor = fns[0]
            others = fns[1:]
            other_desc = ", ".join(f"'{f.name}' at line {f.lineno}" for f in others)
            end = getattr(anchor, "end_lineno", anchor.lineno) or anchor.lineno
            yield Finding(
                file=file.path,
                line=anchor.lineno,
                detector=self.name,
                title=f"Function '{anchor.name}' has duplicate(s) in this file",
                evidence=(
                    f"identical AST shape (modulo local names) as: {other_desc}; "
                    f"a shared helper or parameterisation is likely missing"
                ),
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.MEDIUM,
                end_line=end,
                code_excerpt=file.excerpt(anchor.lineno, min(end, anchor.lineno + 6), context=1),
            )


def _walked_statement_count(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    body = _strip_docstring(fn.body)
    return sum(1 for stmt in body for sub in ast.walk(stmt) if isinstance(sub, ast.stmt))


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _normalized_signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Stable string signature for a function body, ignoring local names.

    Two functions whose bodies differ only in identifier choice will hash to
    the same signature. Operator types and structural shape are preserved.
    """
    name_map: dict[str, str] = {}
    # Seed the rename map with parameters so positional matches survive.
    for param in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs:
        if param.arg not in ("self", "cls"):
            name_map[param.arg] = f"_v{len(name_map)}"

    body = _strip_docstring(fn.body)
    parts: list[str] = []
    for stmt in body:
        _emit(stmt, name_map, parts)
    return "|".join(parts)


def _emit(node: ast.AST, name_map: dict[str, str], out: list[str]) -> None:
    """Append a deterministic token sequence for `node` into `out`.

    Local Name nodes get replaced via name_map; new names allocate a fresh
    `_vN` slot. Non-local names (module-level functions, builtins, attributes)
    are kept as-is so calls to `len`, `range`, `isinstance` etc. still discriminate.
    """
    if isinstance(node, ast.Name):
        # Heuristic: if the name was ever assigned/declared inside the function
        # we'd have caught it via parameters or the LHS-walk below. By the time
        # we reach a Load Name we haven't seen, treat it as a non-local
        # reference and keep its identity — that preserves `len` vs `sum`.
        replacement = name_map.get(node.id, node.id)
        out.append(f"Name:{replacement}")
        return

    if isinstance(node, ast.arg):
        replacement = name_map.setdefault(node.arg, f"_v{len(name_map)}")
        out.append(f"arg:{replacement}")
        return

    type_name = type(node).__name__
    children = list(ast.iter_child_nodes(node))

    # Bind LHS targets BEFORE descending so the RHS Loads see the renamed slot.
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            _bind_targets(target, name_map)
    if isinstance(node, ast.For) or isinstance(node, ast.AsyncFor):
        _bind_targets(node.target, name_map)
    if isinstance(node, ast.comprehension):
        _bind_targets(node.target, name_map)
    if isinstance(node, ast.ExceptHandler) and node.name:
        name_map.setdefault(node.name, f"_v{len(name_map)}")

    extras = _operator_token(node)
    out.append(f"{type_name}({len(children)}){extras}")
    for child in children:
        _emit(child, name_map, out)


def _bind_targets(target: ast.AST, name_map: dict[str, str]) -> None:
    if isinstance(target, ast.Name):
        name_map.setdefault(target.id, f"_v{len(name_map)}")
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _bind_targets(elt, name_map)
        return
    if isinstance(target, ast.Starred):
        _bind_targets(target.value, name_map)


def _operator_token(node: ast.AST) -> str:
    """Return a discriminating tag for nodes whose meaning depends on an operator.

    Without this, `x + y` and `x * y` would share a signature. Same for
    comparisons and boolean ops.
    """
    if isinstance(node, ast.BinOp):
        return f"[{type(node.op).__name__}]"
    if isinstance(node, ast.UnaryOp):
        return f"[{type(node.op).__name__}]"
    if isinstance(node, ast.BoolOp):
        return f"[{type(node.op).__name__}]"
    if isinstance(node, ast.Compare):
        return "[" + ",".join(type(op).__name__ for op in node.ops) + "]"
    if isinstance(node, ast.AugAssign):
        return f"[{type(node.op).__name__}]"
    if isinstance(node, ast.Constant):
        return f"[{type(node.value).__name__}]"
    return ""
