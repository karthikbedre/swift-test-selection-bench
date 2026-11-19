"""Compiler-index selector.

The first tests use a stand-in for tools/index-query and need no Swift toolchain. The rest build the
fixtures with a real toolchain and are skipped when `swift` or the built index-query tool is missing.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from tsel.changes import read_changes
from tsel.graph import load_graph
from tsel.selectors import SELECTORS
from tsel.selectors import compiler_index as ci

from test_selectors import ALL_SAMPLE, ROOT, _git, commit_edit, make_repo

FAKE_HELPER = """#!{python}
import json, os, sys
req = json.load(sys.stdin)
with open(os.environ["FAKE_LOG"], "w") as f:
    json.dump(req, f)
print(os.environ["FAKE_RESPONSE"])
"""


@pytest.fixture()
def sample(tmp_path):
    return make_repo(tmp_path, ROOT / "fixtures" / "sample-modular")


@pytest.fixture()
def fake_index(tmp_path, monkeypatch):
    """Stand-in helper; the 'index build' is the repo itself checked out at base."""
    helper = tmp_path / "fake-index-query"
    helper.write_text(FAKE_HELPER.format(python=sys.executable))
    helper.chmod(helper.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "request.json"
    monkeypatch.setenv("TSEL_INDEX_QUERY", str(helper))
    monkeypatch.setenv("TSEL_LIBINDEXSTORE", "/nonexistent/libIndexStore.so")
    monkeypatch.setenv("FAKE_LOG", str(log))

    def respond(resp: dict):
        monkeypatch.setenv("FAKE_RESPONSE", json.dumps(resp))

    def ensure(self, changes, graph):
        return changes.repo, "/nonexistent/store", 0.0

    monkeypatch.setattr(ci.CompilerIndex, "_ensure_index", ensure)
    return respond, log


def names(sel) -> set[str]:
    return {t.split("::")[1] for t in sel.tests}


def run(repo: Path, base: str, head: str, toolchain: bool = False, **kw):
    graph = load_graph(str(repo), prefer_toolchain=toolchain)
    return ci.CompilerIndex(**kw).select(read_changes(str(repo), base, head), graph)


def test_request_names_the_changed_declaration_and_referring_files_map_to_targets(sample, fake_index):
    respond, log = fake_index
    base, head = commit_edit(sample, "Sources/Models/Character.swift", '"\\(name) #\\(id)"', '"\\(name) (\\(id))"')
    character_list = next(sample.glob("Sources/CharacterFeature/*.swift"))
    respond({"resolved": [], "unresolved": [], "seedSymbols": 1, "visitedSymbols": 1,
             "files": {str(character_list): "CharacterFeature",
                       str(sample / "Sources/Models/Character.swift"): "Models"}})
    sel = run(sample, base, head)
    req = json.loads(log.read_text())
    [item] = req["changes"]
    assert item["mode"] == "range" and item["path"].endswith("Sources/Models/Character.swift")
    assert item["startLine"] <= 11 <= item["endLine"]          # the displayName declaration
    assert req["addedNames"] == []
    # CharacterFeature refers to it; AppCore depends on CharacterFeature; ModelsTests always runs.
    assert names(sel) == {"ModelsTests", "CharacterFeatureTests", "AppCoreTests"}


def test_declaration_missing_from_the_index_falls_back_to_the_graph(sample, fake_index):
    respond, _ = fake_index
    base, head = commit_edit(sample, "Sources/Models/Character.swift", '"\\(name) #\\(id)"', '"\\(name)"')
    respond({"resolved": [], "files": {}, "seedSymbols": 0, "visitedSymbols": 0,
             "unresolved": [{"path": str(sample / "Sources/Models/Character.swift"), "startLine": 11,
                             "endLine": 13, "mode": "range"}]})
    sel = run(sample, base, head)
    assert names(sel) == ALL_SAMPLE
    assert any("not-in-index" in r for r in sel.rules)


def test_comment_only_and_conditional_edits_never_reach_the_index(sample, fake_index):
    respond, log = fake_index
    respond({"files": {}})
    base, head = commit_edit(sample, "Sources/Models/Character.swift", "/// Shown in list rows.", "/// Shown in rows.")
    assert names(run(sample, base, head)) == set()
    base, head = commit_edit(sample, "Sources/Models/Episode.swift", '"Pilot"', '"Pilot (debug)"')
    sel = run(sample, base, head)
    assert names(sel) == ALL_SAMPLE and any("conditional-compilation" in r for r in sel.rules)
    assert not log.exists()


def test_added_declaration_is_sent_by_name(sample, fake_index):
    respond, log = fake_index
    respond({"files": {}})
    base, head = commit_edit(sample, "Sources/Models/Character.swift", "    /// Shown in list rows.",
                             "    public var initials: String { String(name.prefix(1)) }\n\n    /// Shown in list rows.")
    run(sample, base, head)
    assert "initials" in json.loads(log.read_text())["addedNames"]


def test_missing_helper_falls_back_to_the_graph(sample, monkeypatch, tmp_path):
    monkeypatch.setenv("TSEL_INDEX_QUERY", str(tmp_path / "not-built"))
    monkeypatch.setattr(ci, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ci.CompilerIndex, "_ensure_index", lambda self, c, g: (c.repo, "/x", 0.0))
    base, head = commit_edit(sample, "Sources/Models/Character.swift", '"\\(name) #\\(id)"', '"\\(name)"')
    sel = run(sample, base, head)
    assert names(sel) == ALL_SAMPLE


# -- with a real Swift toolchain ------------------------------------------------------------------

def _toolchain_ready() -> bool:
    if not shutil.which("swift"):
        return False
    try:
        ci.find_index_query()
        ci.find_libindexstore()
    except ci.IndexUnavailable:
        return False
    return True


needs_swift = pytest.mark.skipif(not _toolchain_ready(), reason="needs swift and a built tools/index-query")


@needs_swift
def test_real_index_body_edit(sample, tmp_path):
    base, head = commit_edit(sample, "Sources/Models/Character.swift", '"\\(name) #\\(id)"', '"\\(name) (\\(id))"')
    sel = run(sample, base, head, toolchain=True, cache_dir=str(tmp_path / "cache"))
    assert names(sel) == {"ModelsTests", "CharacterFeatureTests", "AppCoreTests"}, sel.rules


@needs_swift
def test_real_index_follows_internal_helper_to_public_api(sample, tmp_path):
    (sample / "Sources/Models/Naming.swift").write_text(
        'enum Naming {\n    static func suffix(_ id: Int) -> String {\n        "#\\(id)"\n    }\n}\n')
    p = sample / "Sources/Models/Character.swift"
    p.write_text(p.read_text().replace('"\\(name) #\\(id)"', '"\\(name) \\(Naming.suffix(id))"'))
    _git(sample, "add", "-A")
    _git(sample, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "helper")
    base, head = commit_edit(sample, "Sources/Models/Naming.swift", '"#\\(id)"', '"No. \\(id)"')
    sel = run(sample, base, head, toolchain=True, cache_dir=str(tmp_path / "cache"))
    assert names(sel) == {"ModelsTests", "CharacterFeatureTests", "AppCoreTests"}, sel.rules


@needs_swift
def test_real_index_misses_trap_t001(tmp_path):
    """The blind spot the trap exists for: string interpolation calls `description` through
    CustomStringConvertible, and the index records no reference from Billing to the protocol
    extension's `description`. BillingTests fails after this edit, and the index skips it."""
    trap_dir = ROOT / "traps" / "T001-protocol-default-description"
    trap = json.loads((trap_dir / "trap.json").read_text())
    repo = make_repo(tmp_path, trap_dir)
    e = trap["edit"]
    base, head = commit_edit(repo, e["file"], e["find"], e["replace"])
    sel = run(repo, base, head, toolchain=True, cache_dir=str(tmp_path / "cache"))
    assert "BillingTests" not in names(sel), "index now records the implicit call; update the trap notes"
