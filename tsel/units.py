"""The test-class pass: units inside test targets, and which units each selector picks.

A unit is a test class: an XCTestCase subclass, or a swift-testing suite (a type holding @Test functions,
with or without @Suite). A type extended across files is one unit with several files. Top-level @Test
functions in a target form the unit TOP_LEVEL. Nested types belong to their outermost type's unit,
which is also how the oracle names them.

Files in a test target that declare no unit are helpers (fixtures, shared setup, extensions on the code
under test). Changed names spread through them: when a helper spells a changed name, the names it
declares count as changed too, until nothing new is added.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from .graph import Graph
from .swiftdecl import analyze

TOP_LEVEL = "(top-level)"
TYPE_KINDS = {"class", "struct", "enum", "actor", "extension"}


@dataclass
class TargetUnits:
    units: dict[str, set[str]] = field(default_factory=dict)        # unit -> files
    spelled: dict[str, set[str]] = field(default_factory=dict)      # file -> names it spells
    declared: dict[str, set[str]] = field(default_factory=dict)     # file -> names it declares
    helpers: set[str] = field(default_factory=set)                  # files with no unit

    def files_of(self, units: set[str]) -> set[str]:
        return {f for u in units for f in self.units.get(u, set())}


def _ls(repo: str, rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", rev, "--", path],
                         capture_output=True, text=True).stdout.splitlines()   # paths may hold spaces
    return [p for p in out if p.endswith(".swift")]


def _show(repo: str, rev: str, path: str) -> bytes:
    return subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"], capture_output=True).stdout


def target_units(repo: str, rev: str, graph: Graph, tid: str) -> TargetUnits:
    t = graph.targets[tid]
    tu = TargetUnits()
    paths = _ls(repo, rev, t.path)
    facts_of = {path: analyze(_show(repo, rev, path)) for path in paths}
    # classes that reach XCTestCase through other classes in the target (class B: A, class A: XCTestCase)
    bases = {d.name: set(d.inherits) for f in facts_of.values() for d in f.decls
             if d.owner is None and d.kind in ("class", "actor")}
    xctest = {"XCTestCase"}
    while True:
        more = {n for n, inh in bases.items() if inh & xctest} - xctest
        if not more:
            break
        xctest |= more
    for path in paths:
        facts = facts_of[path]
        tu.spelled[path] = set(facts.spelled)
        tu.declared[path] = {d.name for d in facts.decls}
        # a nested suite belongs to its outermost type, which is how the oracle names it
        parent = {d.name: d.owner for d in facts.decls if d.kind in TYPE_KINDS and d.owner}

        def outermost(name: str) -> str:
            seen = set()
            while name in parent and name not in seen:
                seen.add(name)
                name = parent[name]
            return name

        test_owners = {outermost(d.owner) for d in facts.decls if "Test" in d.attributes and d.owner}
        found = False
        for d in facts.decls:
            top = d.owner is None
            if top and d.kind in TYPE_KINDS and (
                    set(d.inherits) & xctest or "Suite" in d.attributes or d.name in test_owners):
                tu.units.setdefault(d.name, set()).add(path)
                found = True
            elif top and d.kind == "func" and "Test" in d.attributes:
                tu.units.setdefault(TOP_LEVEL, set()).add(path)
                found = True
        # members declared in an extension of a unit type defined in another file
        for d in facts.decls:
            if d.owner and "Test" in d.attributes:
                tu.units.setdefault(outermost(d.owner), set()).add(path)
                found = True
        if not found:
            tu.helpers.add(path)
    # an extension of an XCTestCase subclass from another file carries test methods without attributes
    for path in list(tu.helpers):
        owners = {d.name for d in facts_of[path].decls if d.kind == "extension"}
        hit = owners & set(tu.units)
        for u in hit:
            tu.units[u].add(path)
        if hit:
            tu.helpers.discard(path)
    return tu


def spread(names: set[str], tu: TargetUnits) -> set[str]:
    names = set(names)
    while True:
        new = set()
        for f in tu.helpers:
            if tu.spelled.get(f, set()) & names:
                new |= tu.declared.get(f, set()) - names
        if not new:
            return names
        names |= new


def units_by_names(tu: TargetUnits, names: set[str]) -> set[str]:
    names = spread(names, tu)
    return {u for u, files in tu.units.items() if any(tu.spelled.get(f, set()) & names for f in files)}


def units_by_files(tu: TargetUnits, files: set[str]) -> set[str]:
    """Units with a file among `files`, or spelling a name declared in a helper among them."""
    picked = {u for u, fs in tu.units.items() if fs & files}
    helper_names = {n for f in files & tu.helpers for n in tu.declared.get(f, set())}
    if helper_names:
        picked |= units_by_names(tu, helper_names)
    return picked


def select_units(name: str, tests: set[str], hints: dict | None, graph: Graph,
                 units_of: dict[str, TargetUnits]) -> tuple[dict[str, set[str]], set[str]]:
    """(unit selection per selected test target, targets kept whole although finer selection was tried)."""
    out: dict[str, set[str]] = {}
    whole: set[str] = set()
    for tid in tests:
        tu = units_of[tid]
        every = set(tu.units)
        if hints is None or tid in hints.get("whole", set()):
            out[tid] = every
            continue
        changed_test_files = {f for f in hints.get("test_files", set()) if graph.owner_of(f) == tid}
        picked: set[str] | None = None
        if changed_test_files:
            # a changed test file: its own units, and units spelling what it declares if it is a helper
            picked = units_by_files(tu, changed_test_files)
        if name == "tree-sitter" and tid in hints.get("spellers", set()):
            picked = (picked or set()) | units_by_names(tu, hints["names"])
        elif name == "compiler-index" and tid in hints.get("referring", set()):
            picked = (picked or set()) | units_by_files(tu, hints["files"] & set(tu.spelled))
        if picked is None:
            out[tid] = every          # reached only through the chain rule, or its own-tests rule
            whole.add(tid)
        else:
            out[tid] = picked
    return out, whole
