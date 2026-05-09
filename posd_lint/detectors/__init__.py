"""Detector registry. Importing a detector module registers via @register decorators."""

import inspect
import logging
from typing import TYPE_CHECKING

from posd_lint.detectors._base import (
    Detector, ProjectDetector,
    DETECTORS, PROJECT_DETECTORS,
)

if TYPE_CHECKING:
    from posd_lint.config import Config


logger = logging.getLogger("posd_lint.detectors")

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
    # Phase 4 — per-file
    duplicate_code,
    cyclomatic_complexity,
    # Phase 3 — project-level
    overexposure,
    temporal_decomposition,
    info_leakage,
    # Phase 4 — project-level
    import_cycle,
    pass_through_variable,
    forbidden_import,
    boundary_violation,
    unstable_interface,
    # Phase 4 — wave D project-level
    pure_function_violation,
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


def detectors_with_config(
    config: "Config | None",
) -> tuple[list[Detector], list[ProjectDetector]]:
    """Instantiate detectors honoring `config`: skip disabled and pass per-detector
    kwargs to constructors. With no config, behaves like all_detectors() +
    all_project_detectors().
    """
    if config is None:
        return all_detectors(), all_project_detectors()

    disabled = set(config.disabled)
    known_names = {cls.name for cls in DETECTORS} | {cls.name for cls in PROJECT_DETECTORS}
    for name in disabled:
        if name not in known_names:
            logger.warning("Disabled detector '%s' is not a registered detector", name)
    for name in config.detector_kwargs:
        if name not in known_names:
            logger.warning("Detector kwargs for unknown detector '%s'", name)

    per_file = [
        _instantiate(cls, config.detector_kwargs.get(cls.name), config)
        for cls in DETECTORS if cls.name not in disabled
    ]
    project = [
        _instantiate(cls, config.detector_kwargs.get(cls.name), config)
        for cls in PROJECT_DETECTORS if cls.name not in disabled
    ]
    return per_file, project


def _instantiate(cls, kwargs: dict | None, config: "Config | None" = None):
    kwargs = dict(kwargs) if kwargs else {}
    if config is not None and _accepts_kwarg(cls, "config") and "config" not in kwargs:
        kwargs["config"] = config
    if not kwargs:
        return cls()
    try:
        return cls(**kwargs)
    except TypeError as e:
        logger.warning(
            "Detector %s rejected config kwargs %s (%s); using defaults",
            cls.name, list(kwargs), e,
        )
        return cls()


def _accepts_kwarg(cls, name: str) -> bool:
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if name in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
