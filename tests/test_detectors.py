"""Per-detector tests against the synthetic corpus.

Each test runs a single detector against its positive and negative corpus
files. The positive must produce ≥1 finding for that detector; the negative
must produce zero. We don't check exact counts — the corpus is small enough
that drift in 'how many findings' isn't usefully diagnostic, and locking it
down would make threshold tuning painful.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from posd_lint.config import load_config
from posd_lint.detectors import (
    boundary_violation,
    comment_repeats_code,
    config_explosion,
    conjoined_methods,
    cyclomatic_complexity,
    duplicate_code,
    forbidden_import,
    forwarded_parameter,
    hard_to_describe,
    import_cycle,
    impl_leaks_into_interface,
    info_leakage,
    overexposure,
    pass_through_method,
    pass_through_variable,
    pure_function_violation,
    repurposed_variable,
    required_call_ordering,
    shallow_class,
    special_general_mixture,
    temporal_decomposition,
    unstable_interface,
    vague_name,
    wide_interface,
)
from posd_lint.parse import iter_python_files, parse_file as _parse
from posd_lint.project import build_project
from posd_lint.parse import parse_file


CORPUS = Path(__file__).parent / "corpus"


def _run(detector, file_path: Path) -> int:
    """Parse + detect; return finding count."""
    parsed = parse_file(file_path)
    assert parsed is not None, f"Failed to parse {file_path}"
    return sum(1 for _ in detector.detect(parsed))


@pytest.mark.parametrize("module,positive,negative", [
    # Phase 1
    (vague_name, "vague_name_positive.py", "vague_name_negative.py"),
    (hard_to_describe, "hard_to_describe_positive.py", "hard_to_describe_negative.py"),
    (config_explosion, "config_explosion_positive.py", "config_explosion_negative.py"),
    (shallow_class, "shallow_class_positive.py", "shallow_class_negative.py"),
    (wide_interface, "wide_interface_positive.py", "wide_interface_negative.py"),
    (comment_repeats_code, "comment_repeats_code_positive.py", "comment_repeats_code_negative.py"),
    # Phase 2
    (pass_through_method, "pass_through_method_positive.py", "pass_through_method_negative.py"),
    (conjoined_methods, "conjoined_methods_positive.py", "conjoined_methods_negative.py"),
    (special_general_mixture, "special_general_mixture_positive.py", "special_general_mixture_negative.py"),
    (repurposed_variable, "repurposed_variable_positive.py", "repurposed_variable_negative.py"),
    (impl_leaks_into_interface, "impl_leaks_into_interface_positive.py", "impl_leaks_into_interface_negative.py"),
    # Phase 3 (per-file)
    (forwarded_parameter, "forwarded_parameter_positive.py", "forwarded_parameter_negative.py"),
    (required_call_ordering, "required_call_ordering_positive.py", "required_call_ordering_negative.py"),
    # Phase 4 (per-file)
    (duplicate_code, "duplicate_code_positive.py", "duplicate_code_negative.py"),
    (cyclomatic_complexity, "cyclomatic_complexity_positive.py", "cyclomatic_complexity_negative.py"),
])
def test_detector_positive_and_negative(module, positive: str, negative: str) -> None:
    """Each detector flags its positive corpus and stays silent on the negative."""
    detector_cls = next(
        cls for name, cls in vars(module).items()
        if isinstance(cls, type) and name.endswith("Detector") and name != "Detector"
        and cls.__module__ == module.__name__
    )
    detector = detector_cls()

    positive_count = _run(detector, CORPUS / positive)
    negative_count = _run(detector, CORPUS / negative)

    assert positive_count >= 1, f"{detector.name} should flag {positive} but didn't"
    assert negative_count == 0, (
        f"{detector.name} false-positive on {negative}: {negative_count} findings"
    )


def test_pass_through_class_detected_specifically() -> None:
    """Targeted: SQLiteStore-style pass-through must be recognized."""
    detector = shallow_class.ShallowClassDetector()
    parsed = parse_file(CORPUS / "shallow_class_positive.py")
    findings = list(detector.detect(parsed))
    assert any("pass-through" in f.title for f in findings), \
        "Pass-through subclass should be detected as such"


def test_wide_interface_lists_method_names() -> None:
    """Evidence string should include the method names — judge needs them."""
    detector = wide_interface.WideInterfaceDetector()
    parsed = parse_file(CORPUS / "wide_interface_positive.py")
    findings = list(detector.detect(parsed))
    assert findings
    assert "create_time_entry" in findings[0].evidence


# Project-level corpora live in a parallel tree because they need real
# directory layouts (multiple files, nested packages).
CORPUS_PROJECTS = Path(__file__).parent / "corpus_projects"


def _project_for(subdir: str):
    """Parse all .py under tests/corpus_projects/<subdir> and return a Project."""
    root = CORPUS_PROJECTS / subdir
    files = []
    for p in iter_python_files(root):
        parsed = _parse(p)
        if parsed is not None:
            files.append(parsed)
    return build_project(files, root=root)


def test_overexposure_positive() -> None:
    """A 12-symbol module imported by 3 callers each using one symbol flags."""
    detector = overexposure.OverexposureDetector()
    project = _project_for("overexposure_yes")
    findings = list(detector.detect_project(project))
    assert any("wide" in f.title for f in findings), \
        f"expected overexposure on `wide` module; got {[f.title for f in findings]}"


def test_overexposure_negative() -> None:
    """A focused 3-symbol module doesn't flag."""
    detector = overexposure.OverexposureDetector()
    project = _project_for("overexposure_no")
    findings = list(detector.detect_project(project))
    assert not findings, f"unexpected findings: {[f.title for f in findings]}"


def test_temporal_decomposition_positive() -> None:
    """Reader/Parser/Processor/Writer in one package flags as a pipeline."""
    detector = temporal_decomposition.TemporalDecompositionDetector()
    project = _project_for("temporal_yes")
    findings = list(detector.detect_project(project))
    assert findings
    assert "FileReader" in findings[0].evidence
    assert "CsvWriter" in findings[0].evidence


def test_info_leakage_positive() -> None:
    """Ticket schema read across 4 external files with 4 distinct attrs flags.

    Also asserts the inferred-receiver-type path: Order is leaked through
    `for o in repo.list_orders()` and `o = fetch_order()` callsites that
    rely on return-annotation inference, not direct `Order(...)` construction.
    """
    detector = info_leakage.InfoLeakageDetector()
    project = _project_for("info_leakage_yes")
    findings = list(detector.detect_project(project))
    titles = [f.title for f in findings]
    assert any("Ticket" in t for t in titles), titles
    assert any("Order" in t for t in titles), titles


def test_import_cycle_positive() -> None:
    """a -> b -> c -> a should produce one cycle finding listing all three files."""
    detector = import_cycle.ImportCycleDetector()
    project = _project_for("import_cycle_yes")
    findings = list(detector.detect_project(project))
    assert len(findings) == 1, f"expected exactly one cycle; got {[f.title for f in findings]}"
    finding = findings[0]
    assert "a.py" in finding.file
    assert "b.py" in finding.evidence
    assert "c.py" in finding.evidence


def test_import_cycle_negative() -> None:
    """A linear x -> y -> z chain has no cycle."""
    detector = import_cycle.ImportCycleDetector()
    project = _project_for("import_cycle_no")
    findings = list(detector.detect_project(project))
    assert not findings, f"unexpected findings: {[f.title for f in findings]}"


def test_pass_through_variable_positive() -> None:
    """outer -> middle -> leaf, where only leaf reads the param, must flag outer."""
    detector = pass_through_variable.PassThroughVariableDetector()
    project = _project_for("pass_through_variable_yes")
    findings = list(detector.detect_project(project))
    assert findings, "expected pass-through finding on outer_fn"
    assert any("outer_fn" in f.title for f in findings), \
        f"expected outer_fn in titles; got {[f.title for f in findings]}"


def test_pass_through_variable_negative() -> None:
    """When middle reads or transforms the param, no pass-through finding."""
    detector = pass_through_variable.PassThroughVariableDetector()
    project = _project_for("pass_through_variable_no")
    findings = list(detector.detect_project(project))
    assert not findings, f"unexpected findings: {[f.title for f in findings]}"


def test_forbidden_import_positive() -> None:
    """A domain file importing sqlalchemy under a banning rule must flag."""
    config = load_config(CORPUS_PROJECTS / "forbidden_import_yes")
    detector = forbidden_import.ForbiddenImportDetector(config=config)
    project = _project_for("forbidden_import_yes")
    findings = list(detector.detect_project(project))
    assert findings, "expected forbidden_import finding"
    assert any("sqlalchemy" in f.title for f in findings), \
        f"expected sqlalchemy in titles; got {[f.title for f in findings]}"


def test_forbidden_import_negative() -> None:
    """Same rule, but the file imports nothing forbidden."""
    config = load_config(CORPUS_PROJECTS / "forbidden_import_no")
    detector = forbidden_import.ForbiddenImportDetector(config=config)
    project = _project_for("forbidden_import_no")
    findings = list(detector.detect_project(project))
    assert not findings, f"unexpected findings: {[f.title for f in findings]}"


def test_boundary_violation_positive() -> None:
    """domain importing infra with allowed_imports.domain=[] must flag."""
    config = load_config(CORPUS_PROJECTS / "boundary_violation_yes")
    detector = boundary_violation.BoundaryViolationDetector(config=config)
    project = _project_for("boundary_violation_yes")
    findings = list(detector.detect_project(project))
    assert findings, "expected boundary violation finding"
    assert any("domain" in f.title and "infra" in f.title for f in findings), \
        f"expected domain->infra in titles; got {[f.title for f in findings]}"


def test_boundary_violation_negative() -> None:
    """Same layer config, but domain imports nothing from infra."""
    config = load_config(CORPUS_PROJECTS / "boundary_violation_no")
    detector = boundary_violation.BoundaryViolationDetector(config=config)
    project = _project_for("boundary_violation_no")
    findings = list(detector.detect_project(project))
    assert not findings, f"unexpected findings: {[f.title for f in findings]}"


def test_pure_function_violation_positive() -> None:
    """Functions named calculate_/parse_/format_ that have effects must flag."""
    detector = pure_function_violation.PureFunctionViolationDetector()
    project = _project_for("pure_function_violation_yes")
    findings = list(detector.detect_project(project))
    assert findings, "expected pure_function_violation finding"
    titles = [f.title for f in findings]
    assert any("calculate_total" in t for t in titles), f"expected calculate_total; got {titles}"


def test_pure_function_violation_negative() -> None:
    """The same prefixes with pure bodies must not flag."""
    detector = pure_function_violation.PureFunctionViolationDetector()
    project = _project_for("pure_function_violation_no")
    findings = list(detector.detect_project(project))
    assert not findings, f"unexpected findings: {[f.title for f in findings]}"


def test_unstable_interface_positive() -> None:
    """A class with importers >= threshold and no Protocol/ABC base flags;
    its sibling Protocol with the same importer count does not."""
    detector = unstable_interface.UnstableInterfaceDetector(threshold=3)
    project = _project_for("unstable_interface_yes")
    findings = list(detector.detect_project(project))
    titles = [f.title for f in findings]
    assert any("BigService" in t and "BigServiceProtocol" not in t for t in titles), \
        f"expected BigService finding; got {titles}"
    assert not any("BigServiceProtocol" in t for t in titles), \
        f"BigServiceProtocol should not flag; got {titles}"
