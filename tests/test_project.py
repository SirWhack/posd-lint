"""Tests for the cross-file Project model.

Focused on Project.call_graph — the cached_property added in Wave A1 that
maps qualified caller name -> set of qualified callee names.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from posd_lint.parse import iter_python_files, parse_file
from posd_lint.project import build_project


CORPUS_PROJECTS = Path(__file__).parent / "corpus_projects"
TIME_TRACKER_SRC = Path("/home/swynn/Code/Time-Tracking-Agent/time-tracker/src")


def _project_for_root(root: Path):
    files = []
    for p in iter_python_files(root):
        parsed = parse_file(p)
        if parsed is not None:
            files.append(parsed)
    return build_project(files, root=root)


def _project_from_sources(tmp_path: Path, sources: dict[str, str]):
    """Materialize a dict of {relpath: source} into a project under tmp_path."""
    for rel, src in sources.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(src)
    return _project_for_root(tmp_path)


def test_call_graph_on_info_leakage_corpus_resolves_without_error() -> None:
    """The info_leakage_yes corpus has no in-function calls — graph is empty
    but construction must succeed and indexes must be consistent."""
    project = _project_for_root(CORPUS_PROJECTS / "info_leakage_yes")
    cg = project.call_graph
    assert isinstance(cg, dict)
    for caller, callees in cg.items():
        assert isinstance(caller, str)
        assert isinstance(callees, set)


def test_call_graph_self_method_call(tmp_path: Path) -> None:
    sources = {
        "mod.py": (
            "class A:\n"
            "    def outer(self):\n"
            "        return self.inner()\n"
            "    def inner(self):\n"
            "        return 1\n"
        ),
    }
    project = _project_from_sources(tmp_path, sources)
    cg = project.call_graph
    assert "mod.A.inner" in cg["mod.A.outer"]


def test_call_graph_typed_local_method_call(tmp_path: Path) -> None:
    sources = {
        "schema.py": (
            "class Thing:\n"
            "    def do(self):\n"
            "        return 1\n"
        ),
        "client.py": (
            "from schema import Thing\n"
            "def use(t: Thing):\n"
            "    return t.do()\n"
        ),
    }
    project = _project_from_sources(tmp_path, sources)
    cg = project.call_graph
    assert "schema.Thing.do" in cg["client.use"]


def test_call_graph_local_var_construction_method_call(tmp_path: Path) -> None:
    sources = {
        "schema.py": (
            "class Thing:\n"
            "    def do(self):\n"
            "        return 1\n"
        ),
        "client.py": (
            "from schema import Thing\n"
            "def make_and_call():\n"
            "    t = Thing()\n"
            "    return t.do()\n"
        ),
    }
    project = _project_from_sources(tmp_path, sources)
    cg = project.call_graph
    assert "schema.Thing.do" in cg["client.make_and_call"]


def test_call_graph_module_qualified_call(tmp_path: Path) -> None:
    sources = {
        "util.py": (
            "def helper():\n"
            "    return 1\n"
        ),
        "client.py": (
            "import util\n"
            "def run():\n"
            "    return util.helper()\n"
        ),
    }
    project = _project_from_sources(tmp_path, sources)
    cg = project.call_graph
    assert "util.helper" in cg["client.run"]


def test_call_graph_bare_top_level_call(tmp_path: Path) -> None:
    sources = {
        "mod.py": (
            "def helper():\n"
            "    return 1\n"
            "def run():\n"
            "    return helper()\n"
        ),
    }
    project = _project_from_sources(tmp_path, sources)
    cg = project.call_graph
    assert "mod.helper" in cg["mod.run"]


def test_call_graph_skips_unknown_calls(tmp_path: Path) -> None:
    """Calls we can't resolve (untyped params, dynamic dispatch) are silently
    dropped. Recall < 1 is a documented design choice."""
    sources = {
        "mod.py": (
            "def run(x):\n"
            "    return x.do_something()\n"
        ),
    }
    project = _project_from_sources(tmp_path, sources)
    cg = project.call_graph
    assert cg.get("mod.run", set()) == set()


def test_call_graph_does_not_double_count_nested_functions(tmp_path: Path) -> None:
    """A call inside a nested def belongs to the nested function, not the outer."""
    sources = {
        "mod.py": (
            "def outer():\n"
            "    def inner():\n"
            "        return helper()\n"
            "    return inner\n"
            "def helper():\n"
            "    return 1\n"
        ),
    }
    project = _project_from_sources(tmp_path, sources)
    cg = project.call_graph
    assert "mod.helper" not in cg.get("mod.outer", set())


@pytest.mark.skipif(not TIME_TRACKER_SRC.exists(), reason="time-tracker source not available")
def test_call_graph_performance_on_time_tracker() -> None:
    """The 45-file time-tracker codebase must build in <1s."""
    files = []
    for p in iter_python_files(TIME_TRACKER_SRC):
        parsed = parse_file(p)
        if parsed is not None:
            files.append(parsed)
    project = build_project(files, root=TIME_TRACKER_SRC)

    t = time.time()
    cg = project.call_graph
    elapsed = time.time() - t
    assert elapsed < 1.0, f"call_graph took {elapsed:.2f}s, expected <1s"
    assert len(cg) > 0, "expected non-empty call graph for time-tracker"
