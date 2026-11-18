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
    for name in ("run-all", "package-graph", "tree-sitter"):
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


def test_body_edit_skips_package_that_never_spells_the_name(sample):
    base, head = commit_edit(sample, "Sources/Models/Character.swift", '"\\(name) #\\(id)"', '"\\(name) (#\\(id))"')
    s = select(sample, base, head)
    assert s["package-graph"] == ALL_SAMPLE
    # CharacterFeature spells displayName; AppCore follows by the chain rule; EpisodeFeature is skipped.
    assert s["tree-sitter"] == {"ModelsTests", "CharacterFeatureTests", "AppCoreTests"}


def test_comment_only_edit_selects_nothing(sample):
    base, head = commit_edit(sample, "Sources/Models/Character.swift", "/// Shown in list rows.", "/// Shown in list rows and headers.")
    s = select(sample, base, head)
    assert s["package-graph"] == ALL_SAMPLE
    assert s["tree-sitter"] == set()
    assert any(r.startswith("trivia-only") for r in s["tree-sitter:rules"])


def test_stored_property_change_widens_to_owner_type(sample):
    base, head = commit_edit(sample, "Sources/Models/Character.swift", "public var name: String",
                             "public var name: String\n    public var status: String = \"Alive\"")
    s = select(sample, base, head)
    # Every module that spells Character is affected; EpisodeFeature never does.
    assert s["tree-sitter"] == {"ModelsTests", "CharacterFeatureTests", "AppCoreTests"}


def test_conditional_compilation_falls_back_to_graph(sample):
    base, head = commit_edit(sample, "Sources/Models/Episode.swift", '"Pilot"', '"Pilot (debug)"')
    s = select(sample, base, head)
    assert s["tree-sitter"] == s["package-graph"] == ALL_SAMPLE
    assert any("conditional-compilation" in r for r in s["tree-sitter:rules"])


def test_manifest_change_selects_everything(sample):
    base, head = commit_edit(sample, "Package.swift", "swift-tools-version: 5.9", "swift-tools-version: 5.10")
    s = select(sample, base, head)
    assert s["tree-sitter"] == s["package-graph"] == s["run-all"] == ALL_SAMPLE


def test_docs_change_selects_nothing(sample):
    (sample / "README.md").write_text("# Sample\n")
    _git(sample, "add", "README.md")
    _git(sample, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "docs")
    base = _git(sample, "rev-parse", "HEAD")
    base, head = commit_edit(sample, "README.md", "# Sample", "# Sample package")
    s = select(sample, base, head)
    assert s["package-graph"] == s["tree-sitter"] == set()


def test_trap_t001_protocol_default_is_caught(tmp_path):
    import json
    trap_dir = ROOT / "traps" / "T001-protocol-default-description"
    trap = json.loads((trap_dir / "trap.json").read_text())
    repo = make_repo(tmp_path, trap_dir)
    e = trap["edit"]
    base, head = commit_edit(repo, e["file"], e["find"], e["replace"])
    s = select(repo, base, head)
    for must in trap["must_select"]:
        assert must in s["package-graph"]
        assert must in s["tree-sitter"], s["tree-sitter:rules"]
    # Reports depends on Core but never touches Formatter, so the syntax selector can skip it.
    assert s["tree-sitter"] == {"BillingTests"}


def test_tree_sitter_never_widens_the_graph(sample):
    for find, rep in [('"\\(name) #\\(id)"', '"\\(name)"'), ("self.code = code", "self.code = code.uppercased()")]:
        path = "Sources/Models/Character.swift" if "name" in find else "Sources/Models/Episode.swift"
        base, head = commit_edit(sample, path, find, rep)
        s = select(sample, base, head)
        assert s["tree-sitter"] <= s["package-graph"]


@pytest.mark.parametrize("path,cls", [
    ("Package.swift", FileClass.MANIFEST), ("Package.resolved", FileClass.MANIFEST),
    ("Sources/A/x.swift", FileClass.SWIFT_SOURCE), ("Tests/ATests/x.swift", FileClass.SWIFT_TEST),
    ("Tests/ATests/Fixtures/a.json", FileClass.RESOURCE), ("Sources/A/Queries/q.graphql", FileClass.GRAPHQL),
    (".github/workflows/ci.yml", FileClass.BUILD_SETTING), ("README.md", FileClass.DOCS),
    ("Sources/A/A.docc/A.md", FileClass.DOCS),
])
def test_classify(path, cls):
    assert classify(path) == cls


def test_internal_helper_change_reaches_dependents_through_its_callers(sample):
    # Route displayName through an internal helper, then change only the helper's body.
    (sample / "Sources/Models/Naming.swift").write_text(
        'enum Naming {\n    static func suffix(_ id: Int) -> String {\n        "#\\(id)"\n    }\n}\n')
    p = sample / "Sources/Models/Character.swift"
    p.write_text(p.read_text().replace('"\\(name) #\\(id)"', '"\\(name) \\(Naming.suffix(id))"'))
    _git(sample, "add", "-A")
    _git(sample, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "helper")
    base, head = commit_edit(sample, "Sources/Models/Naming.swift", '"#\\(id)"', '"No. \\(id)"')
    s = select(sample, base, head)
    # Nobody outside Models spells `suffix`, but displayName uses it and CharacterFeature spells displayName.
    assert s["tree-sitter"] == {"ModelsTests", "CharacterFeatureTests", "AppCoreTests"}


def test_paths_with_spaces_keep_their_line_ranges(sample):
    src = sample / "Sources/Models/Character.swift"
    spaced = sample / "Sources/Models/Character Naming.swift"
    spaced.write_text("extension Character {\n    public var shout: String { name.uppercased() }\n}\n")
    _git(sample, "add", "-A")
    _git(sample, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "spaced")
    base, head = commit_edit(sample, "Sources/Models/Character Naming.swift", "uppercased()", "lowercased()")
    changes = read_changes(str(sample), base, head)
    f = next(c for c in changes.files if c.path.endswith("Character Naming.swift"))
    assert f.new_lines == [(2, 2)]
    assert select(sample, base, head)["tree-sitter"] == {"ModelsTests"}


def test_version_specific_manifest_wins(tmp_path):
    """SwiftPM reads Package@swift-X.Y.swift when the toolchain is at least X.Y; the harness must too."""
    from tsel.replay import manifest_path, manifests_at

    repo = make_repo(tmp_path, ROOT / "fixtures" / "sample-modular")
    text = (repo / "Package.swift").read_text()
    (repo / "Package@swift-5.6.swift").write_text(text.replace("EpisodeFeatureTests", "OnlyInVersionedTests"))
    (repo / "Package@swift-99.swift").write_text("// newer than any toolchain\n")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "versioned")
    head = _git(repo, "rev-parse", "HEAD")
    assert manifest_path(str(repo), head, ".", version=(6, 4, 2)) == "Package@swift-5.6.swift"
    assert manifest_path(str(repo), head, ".", version=(5, 5, 0)) == "Package.swift"
    assert "OnlyInVersionedTests" in manifests_at(str(repo), head, ["."])["."]
