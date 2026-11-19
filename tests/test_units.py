"""The test-class pass: finding units in test targets and picking them from selector evidence."""
from __future__ import annotations

import subprocess
from pathlib import Path

from tsel.graph import load_graph
from tsel.units import TOP_LEVEL, select_units, target_units

MANIFEST = """// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "U",
    targets: [
        .target(name: "Core"),
        .testTarget(name: "CoreTests", dependencies: ["Core"]),
    ]
)
"""
FILES = {
    "Sources/Core/Money.swift": "public struct Money { public var cents: Int; public init(cents: Int) { self.cents = cents } }\n"
                                "public func label(_ m: Money) -> String { \"\\(m.cents)\" }\n",
    "Tests/CoreTests/Fixtures.swift": "import Core\n\nextension Money { static let ten = Money(cents: 10) }\n"
                                      "func makeWallet() -> [Money] { [.ten] }\n",
    "Tests/CoreTests/LabelTests.swift": "import XCTest\nimport Core\n\nfinal class LabelTests: XCTestCase {\n"
                                        "    func testLabel() { XCTAssertEqual(label(.ten), \"10\") }\n}\n",
    "Tests/CoreTests/WalletTests.swift": "import Testing\n\n@Suite struct WalletTests {\n"
                                         "    @Test func count() { #expect(makeWallet().count == 1) }\n}\n",
    "Tests/CoreTests/MathTests.swift": "import Testing\n\n@Test func addition() { #expect(1 + 1 == 2) }\n",
}


def make(tmp_path: Path) -> tuple[str, object]:
    repo = tmp_path / "u"
    for path, text in {"Package.swift": MANIFEST, **FILES}.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                       check=True, capture_output=True)
    return str(repo), load_graph(str(repo), prefer_toolchain=False)


def test_units_and_helpers(tmp_path):
    repo, graph = make(tmp_path)
    tu = target_units(repo, "HEAD", graph, ".::CoreTests")
    assert set(tu.units) == {"LabelTests", "WalletTests", TOP_LEVEL}
    assert tu.helpers == {"Tests/CoreTests/Fixtures.swift"}


def test_names_spread_through_helpers(tmp_path):
    repo, graph = make(tmp_path)
    units_of = {".::CoreTests": target_units(repo, "HEAD", graph, ".::CoreTests")}
    hints = {"names": {"Money"}, "spellers": {".::CoreTests"}, "whole": set(), "test_files": set()}
    picked, whole = select_units("tree-sitter", {".::CoreTests"}, hints, graph, units_of)
    # WalletTests never spells Money, but calls makeWallet, which the fixture file declares and which spells Money
    assert picked[".::CoreTests"] == {"LabelTests", "WalletTests"}
    assert not whole


def test_target_only_selectors_take_every_unit(tmp_path):
    repo, graph = make(tmp_path)
    units_of = {".::CoreTests": target_units(repo, "HEAD", graph, ".::CoreTests")}
    picked, _ = select_units("package-graph", {".::CoreTests"}, None, graph, units_of)
    assert picked[".::CoreTests"] == {"LabelTests", "WalletTests", TOP_LEVEL}


def test_target_without_evidence_is_kept_whole(tmp_path):
    repo, graph = make(tmp_path)
    units_of = {".::CoreTests": target_units(repo, "HEAD", graph, ".::CoreTests")}
    hints = {"names": {"Money"}, "spellers": set(), "whole": set(), "test_files": set()}
    picked, whole = select_units("tree-sitter", {".::CoreTests"}, hints, graph, units_of)
    assert whole == {".::CoreTests"} and len(picked[".::CoreTests"]) == 3


def test_nested_suite_is_its_outer_type(tmp_path):
    repo, graph = make(tmp_path)
    nested = "import Testing\n\nstruct UtilsTests {\n    struct FlatTests {\n        @Test func a() { #expect(true) }\n    }\n}\n"
    (Path(repo) / "Tests/CoreTests/UtilsTests.swift").write_text(nested)
    for args in (["add", "-A"], ["commit", "-qm", "nested"]):
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                       check=True, capture_output=True)
    tu = target_units(repo, "HEAD", graph, ".::CoreTests")
    assert "UtilsTests" in tu.units and "FlatTests" not in tu.units


def test_indirect_xctest_subclass_and_spaces_in_paths(tmp_path):
    repo, graph = make(tmp_path)
    base = "import XCTest\n\nclass BaseTests: XCTestCase {}\n"
    typed = "final class TypedTests: BaseTests {\n    func testA() {}\n}\n"
    (Path(repo) / "Tests/CoreTests/Base.swift").write_text(base)
    (Path(repo) / "Tests/CoreTests/Sub Folder").mkdir()
    (Path(repo) / "Tests/CoreTests/Sub Folder/Typed.swift").write_text(typed)
    for args in (["add", "-A"], ["commit", "-qm", "typed"]):
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                       check=True, capture_output=True)
    tu = target_units(repo, "HEAD", graph, ".::CoreTests")
    assert tu.units["TypedTests"] == {"Tests/CoreTests/Sub Folder/Typed.swift"}


def test_changed_snapshot_keeps_the_target_whole(tmp_path):
    repo, graph = make(tmp_path)
    units_of = {".::CoreTests": target_units(repo, "HEAD", graph, ".::CoreTests")}
    hints = {"names": set(), "spellers": set(), "whole": set(), "test_files": {"Tests/CoreTests/Snapshots/a.txt"}}
    picked, whole = select_units("tree-sitter", {".::CoreTests"}, hints, graph, units_of)
    assert whole == {".::CoreTests"} and len(picked[".::CoreTests"]) == 3
