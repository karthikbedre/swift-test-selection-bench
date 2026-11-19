"""The Bazel hash-cache selector without Bazel: subjects with no Bazel build select everything."""
from __future__ import annotations

from tsel.changes import read_changes
from tsel.graph import load_graph
from tsel.selectors import SELECTORS

from test_selectors import ALL_SAMPLE, ROOT, commit_edit, make_repo


def test_package_without_bazel_selects_everything(tmp_path):
    repo = make_repo(tmp_path, ROOT / "fixtures" / "sample-modular")
    base, head = commit_edit(repo, "Sources/Models/Character.swift", '"\\(name) #\\(id)"', '"\\(name) (#\\(id))"')
    graph = load_graph(str(repo), prefer_toolchain=False)
    sel = SELECTORS["hash-cache"]().select(read_changes(str(repo), base, head), graph)
    assert {t.split("::")[1] for t in sel.tests} == ALL_SAMPLE
    assert sel.all_tests and sel.rules == ["no-bazel-build"]
