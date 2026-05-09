"""Tests for the posd-lint.toml config loader and detector wiring."""

from __future__ import annotations

from pathlib import Path

from posd_lint.config import Config, find_config_path, load_config
from posd_lint.detectors import detectors_with_config
from posd_lint.parse import parse_file


CORPUS = Path(__file__).parent / "corpus"


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_threshold_override_silences_wide_interface(tmp_path: Path) -> None:
    """Raising wide_interface.threshold past the corpus class size yields 0 findings."""
    _write(tmp_path / "posd-lint.toml", '[detectors.wide_interface]\nthreshold = 25\n')
    config = load_config(tmp_path)
    assert config is not None

    per_file, _ = detectors_with_config(config)
    detector = next(d for d in per_file if d.name == "wide_interface")

    parsed = parse_file(CORPUS / "wide_interface_positive.py")
    assert parsed is not None
    findings = list(detector.detect(parsed))
    assert findings == [], f"expected no findings with threshold=25; got {findings}"

    default_per_file, _ = detectors_with_config(None)
    default_detector = next(d for d in default_per_file if d.name == "wide_interface")
    default_findings = list(default_detector.detect(parsed))
    assert default_findings, "sanity: default threshold should still flag the corpus"


def test_disabled_detector_excluded_from_registry(tmp_path: Path) -> None:
    """`disabled = ["repurposed_variable"]` removes the detector from the per-file list."""
    _write(tmp_path / "posd-lint.toml", '[posd-lint]\ndisabled = ["repurposed_variable"]\n')
    config = load_config(tmp_path)
    assert config is not None
    assert "repurposed_variable" in config.disabled

    per_file, project = detectors_with_config(config)
    names = {d.name for d in per_file} | {d.name for d in project}
    assert "repurposed_variable" not in names
    assert "vague_name" in names, "other detectors should still be present"


def test_find_config_walks_up_to_ancestor(tmp_path: Path) -> None:
    """The loader finds posd-lint.toml in any ancestor of the start path."""
    _write(tmp_path / "posd-lint.toml", "[posd-lint]\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    found = find_config_path(nested)
    assert found is not None
    assert found == (tmp_path / "posd-lint.toml").resolve()


def test_no_config_returns_none(tmp_path: Path) -> None:
    """Absent posd-lint.toml means load_config returns None and detectors fall back to defaults."""
    assert load_config(tmp_path) is None

    per_file, project = detectors_with_config(None)
    assert per_file and project


def test_layers_and_imports_loaded_for_b2_b3(tmp_path: Path) -> None:
    """Architecture-rule data is preserved verbatim for downstream detectors."""
    toml = """
[layers]
domain = ["app/domain/**"]
service = ["app/services/**"]

[allowed_imports]
domain = []
service = ["domain"]

[forbidden_imports]
"app/domain/**" = ["sqlalchemy", "requests"]
"""
    _write(tmp_path / "posd-lint.toml", toml)
    config = load_config(tmp_path)
    assert isinstance(config, Config)
    assert config.layers == {"domain": ["app/domain/**"], "service": ["app/services/**"]}
    assert config.allowed_imports == {"domain": [], "service": ["domain"]}
    assert config.forbidden_imports == {"app/domain/**": ["sqlalchemy", "requests"]}
