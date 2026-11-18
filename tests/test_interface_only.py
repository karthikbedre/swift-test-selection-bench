"""The interface-only variant on the sample package."""
from __future__ import annotations

from tsel.changes import read_changes
from tsel.graph import load_graph
from tsel.selectors import SELECTORS
from tsel.selectors.interface_only import closest_tests, public_interface

from test_selectors import ALL_SAMPLE, ROOT, commit_edit, make_repo

import pytest


@pytest.fixture()
def sample(tmp_path):
    return make_repo(tmp_path, ROOT / "fixtures" / "sample-modular")


def interface_only(repo, base, head) -> set[str]:
    graph = load_graph(str(repo), prefer_toolchain=False)
    sel = SELECTORS["interface-only"]().select(read_changes(str(repo), base, head), graph)
    return {t.split("::")[1] for t in sel.tests}


def test_public_interface_ignores_bodies_and_private_declarations():
    a = public_interface(b"public struct S {\n public var x: Int { 1 }\n private func f() -> Int { 2 }\n}\n")
    b = public_interface(b"public struct S {\n public var x: Int { 1 + 0 }\n private func f(y: Int) -> Int { 3 }\n}\n")
    assert a == b
    c = public_interface(b"public struct S {\n public var x: Int { 1 }\n public func g() {}\n}\n")
    assert a != c


def test_public_initial_value_is_not_interface():
    assert public_interface(b"public enum E { public static let n = 1 }\n") == \
        public_interface(b"public enum E { public static let n = 2 }\n")


def test_closest_tests_are_the_targets_own(sample):
    graph = load_graph(str(sample), prefer_toolchain=False)
    assert {t.split("::")[1] for t in closest_tests(graph, ".::Models")} == {"ModelsTests"}


def test_body_edit_stays_in_the_changed_target(sample):
    base, head = commit_edit(sample, "Sources/Models/Character.swift", '"\\(name) #\\(id)"', '"\\(name) (#\\(id))"')
    assert interface_only(sample, base, head) == {"ModelsTests"}


def test_public_signature_edit_reaches_dependents(sample):
    base, head = commit_edit(sample, "Sources/Models/Character.swift",
                             "public var displayName: String {", "public var displayName: String? {")
    assert interface_only(sample, base, head) == ALL_SAMPLE
