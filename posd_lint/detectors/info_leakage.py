"""Class attributes read from many external files (PoSD §6).

Ousterhout's information leakage: 'a design decision is reflected in multiple
modules.' If a class's public attributes — its schema — are read directly by
many files outside the class's own module, the schema is leaked. A change to
the schema requires editing every reader; the class isn't really hiding
anything.

Detection shape (project-level):
- For each defined class, count distinct external files that read ≥1 of its
  public instance attributes.
- Threshold: ≥4 external readers across ≥3 distinct attributes = leak.
- The two thresholds together avoid two false-positive classes:
  * "many files read one common attr" (e.g. `entry.id`) — that's a normal
    facade access, not schema leakage.
  * "one file reads many attrs" (a serializer or test) — legitimate consumer.

The judge gets the class name, the leaked attribute names, and the external
files, and decides whether the schema should move into the class or whether
this is an acceptable data-class pattern.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from posd_lint.detectors._base import ProjectDetector, register_project
from posd_lint.findings import Finding, Severity
from posd_lint.project import Project


THRESHOLD_EXTERNAL_READERS = 4
THRESHOLD_DISTINCT_ATTRS = 3


@register_project
class InfoLeakageDetector(ProjectDetector):
    name = "info_leakage"
    title = "Class schema is read from many external files"
    rubric_ref = "6"
    rubric_title = "Information hiding vs. information leakage"

    def detect_project(self, project: Project) -> Iterable[Finding]:
        accesses = project.public_class_attributes
        defining_file_by_class: dict[str, str] = {
            name: refs[0].file
            for name, refs in project.classes_by_name.items()
        }

        for class_name, sites in accesses.items():
            defining_file = defining_file_by_class.get(class_name)
            if not defining_file:
                continue
            external_sites = [s for s in sites if s.file != defining_file]
            if not external_sites:
                continue

            # Group: which external files read which attrs of this class?
            files_to_attrs: dict[str, set[str]] = defaultdict(set)
            for s in external_sites:
                files_to_attrs[s.file].add(s.attr)
            distinct_attrs = {a for attrs in files_to_attrs.values() for a in attrs}

            if len(files_to_attrs) < THRESHOLD_EXTERNAL_READERS:
                continue
            if len(distinct_attrs) < THRESHOLD_DISTINCT_ATTRS:
                continue

            # Find the class def line in its defining file.
            line = next(
                (ref.node.lineno for ref in project.classes_by_name[class_name]
                 if ref.file == defining_file),
                1,
            )

            external_paths = sorted(files_to_attrs.keys())
            shown_files = ", ".join(Path(p).name for p in external_paths[:5])
            if len(external_paths) > 5:
                shown_files += f" (+{len(external_paths) - 5} more)"

            yield Finding(
                file=defining_file,
                line=line,
                detector=self.name,
                title=f"Class '{class_name}' schema is read across {len(files_to_attrs)} external files",
                evidence=(
                    f"{len(distinct_attrs)} attrs ({', '.join(sorted(distinct_attrs))}) "
                    f"read in: {shown_files}"
                ),
                rubric_ref=self.rubric_ref,
                rubric_title=self.rubric_title,
                severity=Severity.MEDIUM,
                code_excerpt=f"  class {class_name}: ...\n  read from: {shown_files}",
            )
