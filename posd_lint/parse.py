"""File discovery, AST parsing, and excerpt extraction.

Comments aren't preserved in the standard ast module, so the comment-repeats-code
detector also needs raw source — we provide both. tokenize is used for comment
extraction since we don't need full reparse.
"""

from __future__ import annotations

import ast
import io
import os
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".tox", "build", "dist", ".eggs"}


@dataclass
class ParsedFile:
    """A successfully parsed Python source file.

    source is the raw text (newline-preserving). lines is a 1-indexed list
    where lines[1] is the first line — pad index 0 with empty string so
    detectors can use line numbers directly.
    """
    path: str
    source: str
    tree: ast.Module
    lines: list[str]

    def excerpt(self, start_line: int, end_line: int, context: int = 5) -> str:
        """Return a fenced excerpt with ±context lines, line numbers prefixed.

        Used by the judge to show Claude the surrounding code, not just the
        triggering line. Defaults to 5 lines context which is usually enough
        for class/function-level findings without bloating the prompt.
        """
        lo = max(1, start_line - context)
        hi = min(len(self.lines) - 1, end_line + context)
        out = []
        for i in range(lo, hi + 1):
            marker = ">>" if start_line <= i <= end_line else "  "
            out.append(f"{marker} {i:4d}  {self.lines[i].rstrip()}")
        return "\n".join(out)


@dataclass
class CommentToken:
    """A single comment token with its position."""
    line: int
    col: int
    text: str  # full token text including the leading '#'


def iter_python_files(root: Path) -> Iterator[Path]:
    """Yield .py files under root, skipping common build/venv directories.

    Directory pruning happens in-place on the os.walk dirs list — saves
    walking into massive node_modules trees that aren't ours to lint.
    """
    if root.is_file():
        if root.suffix == ".py":
            yield root
        return

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def parse_file(path: Path) -> ParsedFile | None:
    """Parse a single file. Returns None on syntax error (detector loop continues).

    We attach parent pointers to every node — many detectors need to ask
    "what's the enclosing function/class?" and ast doesn't track that natively.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]

    lines = [""] + source.splitlines()  # 1-index padding
    return ParsedFile(path=str(path), source=source, tree=tree, lines=lines)


def extract_comments(source: str) -> list[CommentToken]:
    """Pull all # comments from source, with line/column positions.

    tokenize handles encoding declarations and string-vs-comment ambiguity
    that a regex would get wrong. Used only by the comment-repeats-code
    detector — most detectors don't need this.
    """
    comments: list[CommentToken] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                line, col = tok.start
                comments.append(CommentToken(line=line, col=col, text=tok.string))
    except tokenize.TokenizeError:
        pass
    return comments
