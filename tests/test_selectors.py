"""Selector behaviour on the sample package and trap T001. Needs git and the Python deps only."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tsel.changes import FileClass, classify, read_changes
from tsel.graph import load_graph
from tsel.selectors import SELECTORS

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def make_repo(tmp_path: Path, src: Path) -> Path:
    repo = tmp_path / src.name
    shutil.copytree(src, repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    return repo


def commit_edit(repo: Path, path: str, find: str, replace: str) -> tuple[str, str]:
    base = _git(repo, "rev-parse", "HEAD")
    p = repo / path
    text = p.read_text()
    assert find in text, f"{find!r} not in {path}"
    p.write_text(text.replace(find, replace, 1))
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-am", "edit")
    return base, _git(repo, "rev-parse", "HEAD")


def select(repo: Path, base: str, head: str) -> dict[str, set[str]]:
    graph = load_graph(str(repo), prefer_toolchain=False)
    changes = read_changes(str(repo), base, head)
    out = {}
    for name in ('run-all', 'package-graph'):
        sel = SELECTORS[name]().select(changes, graph)
        out[name] = {t.split("::")[1] for t in sel.tests}
        out[name + ":rules"] = sel.rules
    return out


ALL_SAMPLE = {"ModelsTests", "CharacterFeatureTests", "EpisodeFeatureTests", "AppCoreTests"}


@pytest.fixture()
def sample(tmp_path):
    return make_repo(tmp_path, ROOT / "fixtures" / "sample-modular")


def test_manifest_reader_matches_declared_graph(sample):
    g = load_graph(str(sample), prefer_toolchain=False)
    deps = {t.name: {d.split("::")[1] for d in t.deps} for t in g.targets.values()}
    assert deps["AppCore"] == {"Models", "CharacterFeature", "EpisodeFeature"}
    assert deps["EpisodeFeatureTests"] == {"EpisodeFeature"}
    assert g.owner_of("Sources/Models/Character.swift") == ".::Models"
    assert g.owner_of("README.md") is None


def test_manifest_change_selects_everything(sample):
    base, head = commit_edit(sample, "Package.swift", "swift-tools-version: 5.9", "swift-tools-version: 5.10")
    s = select(sample, base, head)
    assert s["package-graph"] == s["run-all"] == ALL_SAMPLE


def test_docs_change_selects_nothing(sample):
    (sample / "README.md").write_text("# Sample\n")
    _git(sample, "add", "README.md")
    _git(sample, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "docs")
    base = _git(sample, "rev-parse", "HEAD")
    base, head = commit_edit(sample, "README.md", "# Sample", "# Sample package")
    s = select(sample, base, head)
    assert s["package-graph"] == set()


@pytest.mark.parametrize("path,cls", [
    ("Package.swift", FileClass.MANIFEST), ("Package.resolved", FileClass.MANIFEST),
    ("Sources/A/x.swift", FileClass.SWIFT_SOURCE), ("Tests/ATests/x.swift", FileClass.SWIFT_TEST),
    ("Tests/ATests/Fixtures/a.json", FileClass.RESOURCE), ("Sources/A/Queries/q.graphql", FileClass.GRAPHQL),
    (".github/workflows/ci.yml", FileClass.BUILD_SETTING), ("README.md", FileClass.DOCS),
    ("Sources/A/A.docc/A.md", FileClass.DOCS),
])
def test_classify(path, cls):
    assert classify(path) == cls
