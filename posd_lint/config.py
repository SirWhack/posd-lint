"""TOML config loader for posd-lint.

A `posd-lint.toml` placed in the project root (or any ancestor of the target
path) is auto-discovered by the CLI. The file declares per-detector threshold
overrides, disabled detectors, and architecture-rule data (layers,
allowed_imports, forbidden_imports) which Wave B2/B3 detectors consume.

Schema:

    [posd-lint]
    rubric = "posd-reference.md"           # optional; overrides bundled rubric
    disabled = ["repurposed_variable"]      # detectors to skip entirely

    [detectors.<name>]
    <kwarg> = <value>                      # passed to detector constructor

    [layers]
    domain = ["app/domain/**"]
    [allowed_imports]
    domain = []
    [forbidden_imports]
    "app/domain/**" = ["sqlalchemy"]

Validation is intentionally lenient — unknown top-level keys produce warnings
(via the logger) rather than errors so users can experiment without breakage.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


logger = logging.getLogger("posd_lint.config")

CONFIG_FILENAME = "posd-lint.toml"

KNOWN_TOP_LEVEL_KEYS = frozenset({
    "posd-lint",
    "detectors",
    "layers",
    "allowed_imports",
    "forbidden_imports",
})

KNOWN_POSD_LINT_KEYS = frozenset({"rubric", "disabled"})


@dataclass
class Config:
    rubric_path: Path | None = None
    disabled: tuple[str, ...] = ()
    detector_kwargs: dict[str, dict[str, Any]] = field(default_factory=dict)
    layers: dict[str, list[str]] = field(default_factory=dict)
    allowed_imports: dict[str, list[str]] = field(default_factory=dict)
    forbidden_imports: dict[str, list[str]] = field(default_factory=dict)
    source_path: Path | None = None


def find_config_path(start: Path) -> Path | None:
    """Walk parent directories from `start` up to root, returning the first
    `posd-lint.toml` found. `start` may be a file or directory."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def load_config(start: Path) -> Config | None:
    """Discover and parse a `posd-lint.toml` at or above `start`. Returns
    None if no config is found. Raises on malformed TOML; warns on unknown keys.
    """
    path = find_config_path(start)
    if path is None:
        return None
    with path.open("rb") as f:
        data = tomllib.load(f)
    return _build_config(data, path)


def _build_config(data: dict[str, Any], source: Path) -> Config:
    for key in data:
        if key not in KNOWN_TOP_LEVEL_KEYS:
            logger.warning("Unknown config section [%s] in %s", key, source)

    posd = data.get("posd-lint", {}) or {}
    for key in posd:
        if key not in KNOWN_POSD_LINT_KEYS:
            logger.warning("Unknown key [posd-lint].%s in %s", key, source)

    rubric = posd.get("rubric")
    rubric_path = (source.parent / rubric).resolve() if rubric else None

    disabled = tuple(posd.get("disabled", ()) or ())

    raw_detectors = data.get("detectors", {}) or {}
    detector_kwargs: dict[str, dict[str, Any]] = {
        name: dict(kwargs) for name, kwargs in raw_detectors.items()
        if isinstance(kwargs, dict)
    }

    return Config(
        rubric_path=rubric_path,
        disabled=disabled,
        detector_kwargs=detector_kwargs,
        layers={k: list(v) for k, v in (data.get("layers", {}) or {}).items()},
        allowed_imports={k: list(v) for k, v in (data.get("allowed_imports", {}) or {}).items()},
        forbidden_imports={k: list(v) for k, v in (data.get("forbidden_imports", {}) or {}).items()},
        source_path=source,
    )
