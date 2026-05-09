"""Detector registry. Importing a detector module registers via @register decorators."""

from posd_lint.detectors._base import (
    Detector, ProjectDetector,
    DETECTORS, PROJECT_DETECTORS,
)

# Side-effect imports — each module appends its class to the right registry.
from posd_lint.detectors import (  # noqa: F401
    # Phase 1 — per-file
    vague_name,
    hard_to_describe,
    config_explosion,
    shallow_class,
    wide_interface,
    comment_repeats_code,
    # Phase 2 — per-file
    pass_through_method,
    conjoined_methods,
    special_general_mixture,
    repurposed_variable,
    impl_leaks_into_interface,
    # Phase 3 — per-file
    forwarded_parameter,
    required_call_ordering,
    # Phase 3 — project-level
    overexposure,
    temporal_decomposition,
    info_leakage,
)


def all_detectors() -> list[Detector]:
    """Instantiate every registered per-file detector with default thresholds."""
    return [cls() for cls in DETECTORS]


def all_project_detectors() -> list[ProjectDetector]:
    """Instantiate every registered project-level detector."""
    return [cls() for cls in PROJECT_DETECTORS]


def detectors_by_name(names: list[str]) -> tuple[list[Detector], list[ProjectDetector]]:
    """Instantiate the named subset across both registries.

    Returns (per_file_detectors, project_detectors). Raises on unknown name.
    """
    per_file = {cls.name: cls for cls in DETECTORS}
    project = {cls.name: cls for cls in PROJECT_DETECTORS}
    known = per_file.keys() | project.keys()
    missing = [n for n in names if n not in known]
    if missing:
        listing = ", ".join(sorted(known))
        raise ValueError(f"Unknown detectors: {missing}. Known: {listing}")
    return (
        [per_file[n]() for n in names if n in per_file],
        [project[n]() for n in names if n in project],
    )
