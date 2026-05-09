"""Pipeline-shaped class clusters in a single package (PoSD §6).

Ousterhout's flagship leakage anti-pattern: code organised by *when* things
happen rather than *what knowledge* is needed. Reader → Parser → Processor →
Writer is the canonical example. Adjacent stages share format knowledge, so
the same design decision (the file format, the protocol layout) is now
smeared across multiple modules.

Detection shape (project-level, heuristic):
- Find classes whose names end in pipeline-suffixes (Reader, Parser, Loader,
  Processor, Transformer, Validator, Formatter, Encoder, Decoder, Writer,
  Importer, Exporter, Builder).
- Group them by package directory.
- If a single package contains ≥3 such classes, flag the package — that's
  almost always temporal decomposition rather than coincidence.

False positives are real (e.g. a 'parsers' package legitimately holds many
parsers, no smell). The AI judge gets the class list and the package and
decides whether they're a pipeline (smell) or a parallel set (fine).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project


# Suffixes that strongly suggest "this class is a stage in a pipeline."
# Order intentional: longer suffixes first so 'Transformer' wins over 'er'.
PIPELINE_SUFFIXES = (
    "Reader", "Writer", "Parser", "Loader", "Processor", "Transformer",
    "Validator", "Formatter", "Encoder", "Decoder", "Importer", "Exporter",
    "Builder", "Compiler", "Renderer", "Serializer", "Deserializer",
)

THRESHOLD_PIPELINE_CLASSES = 3


@register_project
class TemporalDecompositionDetector(ProjectDetector):
    name = "temporal_decomposition"
    title = "Temporal decomposition (pipeline classes in one package)"
    rubric_ref = "6"
    rubric_title = "Information hiding vs. information leakage"

    def detect_project(self, project: Project) -> Iterable[Finding]:
        # Group pipeline-suffixed classes by their containing directory.
        by_package: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
        for class_name, refs in project.classes_by_name.items():
            suffix = self._pipeline_suffix(class_name)
            if not suffix:
                continue
            for ref in refs:
                package_dir = str(Path(ref.file).parent)
                by_package[package_dir].append((class_name, ref.file, ref.node.lineno))

        for package_dir, entries in by_package.items():
            if len(entries) < THRESHOLD_PIPELINE_CLASSES:
                continue
            # Use the first file as the finding's anchor; describe the cluster.
            first_file = entries[0][1]
            first_line = entries[0][2]
            class_list = ", ".join(sorted({name for name, _, _ in entries}))
            yield Finding(
                file=first_file,
                line=first_line,
                detector=self.name,
                title=f"{len(entries)} pipeline-suffixed classes in {Path(package_dir).name}/",
                evidence=f"classes: {class_list}",
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.MEDIUM,
                code_excerpt=f"  package: {package_dir}\n  classes: {class_list}",
            )

    @staticmethod
    def _pipeline_suffix(class_name: str) -> str:
        """Return the matched suffix, or '' if class_name doesn't end with one.

        A class literally named `Parser` (no prefix) is still a pipeline-shape
        class — only excluded if the name is purely the suffix and clearly
        abstract (e.g. ABCs whose name *is* the role). Most concrete code
        names classes after their content (`JsonParser`, `LogReader`) so this
        is rarely the deciding factor."""
        for suffix in PIPELINE_SUFFIXES:
            if class_name.endswith(suffix):
                return suffix
        return ""
