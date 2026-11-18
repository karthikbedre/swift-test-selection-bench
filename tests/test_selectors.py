"""Selector behaviour on the sample package and trap T001. Needs git and the Python deps only."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tsel.changes import FileClass, classify, read_changes
from tsel.graph import load_graph

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


@pytest.mark.parametrize("path,cls", [
    ("Package.swift", FileClass.MANIFEST), ("Package.resolved", FileClass.MANIFEST),
    ("Sources/A/x.swift", FileClass.SWIFT_SOURCE), ("Tests/ATests/x.swift", FileClass.SWIFT_TEST),
    ("Tests/ATests/Fixtures/a.json", FileClass.RESOURCE), ("Sources/A/Queries/q.graphql", FileClass.GRAPHQL),
    (".github/workflows/ci.yml", FileClass.BUILD_SETTING), ("README.md", FileClass.DOCS),
    ("Sources/A/A.docc/A.md", FileClass.DOCS),
])
def test_classify(path, cls):
    assert classify(path) == cls
