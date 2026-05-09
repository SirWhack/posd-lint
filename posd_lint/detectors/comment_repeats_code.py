"""Comments that paraphrase the next line of code (PoSD §12).

The classic '# increment counter' above 'counter += 1'. Such comments add
tokens, not abstraction; they're the noise Ousterhout calls out as the most
common comment failure.

Heuristic: tokenize the comment and the next line of code (after stripping
operators/punctuation), compare normalized word sets. If overlap is high
relative to comment length, flag.

Skipped: TODO/FIXME/XXX/NOTE/HACK markers (those have other purposes), block
header comments (style: long divider lines), and comments that introduce a
section rather than restating one line.
"""

from __future__ import annotations

import re
from typing import Iterable

from posd_lint.detectors._base import Detector, register
from posd_lint.findings import Finding, Severity
from posd_lint.parse import ParsedFile, extract_comments


SIMILARITY_THRESHOLD = 0.6        # Jaccard threshold over word sets
MIN_COMMENT_WORDS = 2              # tiny comments aren't worth flagging
MARKERS = re.compile(r"^\s*(TODO|FIXME|XXX|NOTE|HACK|BUG|WARNING)\b", re.IGNORECASE)
DIVIDER = re.compile(r"^[\s#=\-*_]+$")  # stylistic header lines, not real comments

# Stopwords that shouldn't count toward similarity. Mostly Python-flavor
# code keywords and English filler that happens to appear in both code and
# comments — overlap on these is meaningless.
STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "this", "that", "of", "for", "to", "in",
    "and", "or", "not", "if", "else", "with", "from", "as", "by", "on",
    "self", "cls", "true", "false", "none",
})

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@register
class CommentRepeatsCodeDetector(Detector):
    name = "comment_repeats_code"
    title = "Comment paraphrases the code below"
    rubric_ref = "12"
    rubric_title = "Why write comments"

    def __init__(self, threshold: float = SIMILARITY_THRESHOLD):
        self.threshold = threshold

    def detect(self, file: ParsedFile) -> Iterable[Finding]:
        comments = extract_comments(file.source)
        for comment in comments:
            text = comment.text.lstrip("#").strip()
            if MARKERS.match(comment.text):
                continue
            if DIVIDER.match(comment.text):
                continue
            if not text:
                continue

            comment_words = self._tokens(text)
            if len(comment_words) < MIN_COMMENT_WORDS:
                continue

            next_code = self._next_code_line(file, comment.line)
            if not next_code:
                continue
            code_words = self._tokens(next_code)
            if not code_words:
                continue

            similarity = self._jaccard(comment_words, code_words)
            if similarity < self.threshold:
                continue

            yield Finding(
                file=file.path,
                line=comment.line,
                detector=self.name,
                title="Comment paraphrases the next line",
                evidence=f"word overlap {similarity:.0%} between comment and following statement",
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.LOW,
                code_excerpt=file.excerpt(comment.line, comment.line + 1, context=1),
            )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {w.lower() for w in WORD.findall(text) if w.lower() not in STOPWORDS and len(w) > 1}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    @staticmethod
    def _next_code_line(file: ParsedFile, comment_line: int) -> str:
        """First non-blank, non-comment line at or below comment_line+1."""
        for i in range(comment_line + 1, len(file.lines)):
            line = file.lines[i].strip()
            if not line or line.startswith("#"):
                continue
            return line
        return ""
