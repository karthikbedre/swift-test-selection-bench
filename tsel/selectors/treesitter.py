"""The Tree-sitter syntax selector.

For each target that owns a changed Swift file (an "origin"):

1. Map changed lines to the smallest declarations around them, in the old and the new file.
2. Sort the change: trivia only (comments, whitespace), an edit inside a declaration, an added or
   removed declaration or conformance, a stored-property change.
3. Turn it into a set of changed names. Members Swift calls on its own (description, body, hash,
   encode, CodingKeys, init, ...) widen to their owning type; protocol and protocol-extension members
   widen to the protocol and every type in scope that conforms to it.
4. Within the package-graph bound, a target that spells a changed name is affected, and so is every
   target that depends on an affected target (the chain rule). The origin's own test target always runs.
5. Fall back to the package graph for that origin whenever syntax cannot settle the question:
   macros and macro-like attributes, custom operators, property wrappers, result builders,
   conditional compilation, top-level code, line-sensitive files and files that do not parse.

The answer is a subset of the package-graph answer by construction: it can narrow it, never widen it.
"""
from __future__ import annotations

import re
import subprocess
from functools import lru_cache

from ..changes import ChangeSet, FileChange, file_at
from ..graph import Graph
from ..swiftdecl import (IMPLICIT_MEMBERS, RISKY_ATTRIBUTES, FileFacts, analyze, innermost, macro_like)
from .base import Selection, Selector, route

TYPE_KINDS = {"struct", "class", "enum", "actor", "extension", "protocol", "type"}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Fallback(Exception):
    pass


class TreeSitterSelector(Selector):
    name = "tree-sitter"

    def __init__(self, own_tests_always: bool = True):
        self.own_tests_always = own_tests_always

    # -- reading files ----------------------------------------------------------------------
    @staticmethod
    @lru_cache(maxsize=4096)
    def _facts(repo: str, rev: str, path: str) -> FileFacts | None:
        src = file_at(repo, rev, path)
        return analyze(src) if src is not None else None

    @staticmethod
    @lru_cache(maxsize=1024)
    def _files_under(repo: str, rev: str, path: str) -> tuple[str, ...]:
        out = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", rev, "--", path],
                             capture_output=True, text=True).stdout
        return tuple(p for p in out.splitlines() if p.endswith(".swift"))

    def _target_facts(self, repo: str, rev: str, graph: Graph, tid: str) -> list[FileFacts]:
        t = graph.targets[tid]
        out = []
        for p in self._files_under(repo, rev, t.path):
            # nested targets own their own files
            if graph.owner_of(p) != tid:
                continue
            f = self._facts(repo, rev, p)
            if f is not None:
                out.append(f)
        return out

    # -- step 1-3: changed names for one file ------------------------------------------------
    def _names_for_file(self, changes: ChangeSet, f: FileChange, protocols: set[str], rules: list[str]) -> set[str]:
        old = self._facts(changes.repo, changes.base, f.old_path or f.path) if f.status != "A" else None
        new = self._facts(changes.repo, changes.head, f.path) if f.status != "D" else None
        if old is not None and new is not None and old.leaf_signature == new.leaf_signature:
            if old.line_sensitive or new.line_sensitive:
                raise Fallback(f"line-sensitive:{f.path}")
            rules.append(f"trivia-only:{f.path}")
            return set()

        if f.status in ("M", "R") and not (f.old_lines or f.new_lines):
            raise Fallback(f"no-diff-ranges:{f.path}")  # never guess: an unread diff selects like the graph

        names: set[str] = set()
        changed: list = []
        for facts, ranges in ((old, f.old_lines), (new, f.new_lines)):
            if facts is None:
                continue
            if f.status in ("A", "D"):
                if facts.has_error:
                    raise Fallback(f"parse-error:{f.path}")
                changed.extend(facts.decls)
                continue
            for (a, b) in ranges:
                hits = innermost(facts.decls, a, b)
                spans = [(a, b)] + [(d.start, d.end) for d in hits]
                if any(ea <= sb and eb >= sa for (ea, eb) in facts.error_lines for (sa, sb) in spans):
                    raise Fallback(f"parse-error:{f.path}:{a}")
                if not hits:
                    raise Fallback(f"top-level:{f.path}:{a}")
                changed.extend(hits)
                for msg in facts.risky:
                    line = int(msg.rsplit(" ", 1)[-1])
                    if a <= line <= b:
                        raise Fallback(f"{msg.split(' at ')[0]}:{f.path}:{line}")

        # added or removed declarations (overload shifts, new witnesses) count by key
        if old is not None and new is not None:
            ok = {d.key for d in old.decls}
            nk = {d.key for d in new.decls}
            added_removed = ok ^ nk
            changed.extend(d for d in old.decls + new.decls if d.key in added_removed)

        by_name = {}
        for facts in (old, new):
            if facts is not None:
                for d in facts.decls:
                    if d.kind in TYPE_KINDS:
                        by_name.setdefault(d.name, []).append(d)

        for d in changed:
            if d.in_conditional:
                raise Fallback(f"conditional-compilation:{f.path}:{d.start}")
            owner_attrs = [a for od in by_name.get(d.owner or "", []) for a in od.attributes]
            attrs = d.attributes + owner_attrs
            risky = [a for a in attrs if a in RISKY_ATTRIBUTES]
            if risky:
                raise Fallback(f"attribute@{risky[0]}:{f.path}:{d.start}")
            macro = macro_like(attrs)
            if macro:
                raise Fallback(f"macro-attribute@{macro[0]}:{f.path}:{d.start}")
            if d.kind in ("macro", "operator", "precedencegroup"):
                raise Fallback(f"{d.kind}-declaration:{f.path}:{d.start}")

            names |= names_of_decl(d, protocols)
            if d.kind in TYPE_KINDS:
                names.update(d.inherits)
        return names

    # -- step 4-5 -----------------------------------------------------------------------------
    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        # evidence for the test-class pass (tsel/units.py); not part of the target selection
        self.hints = {"names": set(), "spellers": set(), "whole": set(), "test_files": set()}
        r = route(changes, graph)
        if r.all_tests_reasons:
            self.hints["whole"] = set(graph.test_targets())
            return Selection(self.name, graph.test_targets(), all_tests=True, rules=r.all_tests_reasons)

        rules: list[str] = []
        tests: set[str] = set(r.test_targets)
        self.hints["test_files"] = {f.path for f in changes.files if graph.owner_of(f.path) in r.test_targets}

        for origin, reasons in r.coarse_origins.items():
            rules.extend(f"fallback:{x}" for x in reasons)
            tests |= self.graph_tests(graph, {origin})
            self.hints["whole"] |= self.graph_tests(graph, {origin})

        for origin, files in r.source_changes.items():
            bound = graph.transitive_dependents({origin})
            facts_by_target = {tid: self._target_facts(changes.repo, changes.head, graph, tid) for tid in bound}
            protocols = {p for fl in facts_by_target.values() for fx in fl for p in fx.protocols}
            conformances: dict[str, set[str]] = {}
            for fl in facts_by_target.values():
                for fx in fl:
                    for t, inh in fx.conformances.items():
                        conformances.setdefault(t, set()).update(inh)
            try:
                names: set[str] = set()
                for f in files:
                    names |= self._names_for_file(changes, f, protocols, rules)
            except Fallback as fb:
                rules.append(f"fallback:{fb}")
                tests |= self.graph_tests(graph, {origin})
                self.hints["whole"] |= self.graph_tests(graph, {origin})
                continue

            if names:
                names = _propagate_within(names, facts_by_target[origin], protocols)
            names = _expand_conformers(names, conformances)
            if not names:
                continue  # trivia-only edits: nothing can fail
            rules.append(f"names:{graph.targets[origin].name}:{','.join(sorted(names)[:20])}")

            spellers = {tid for tid in bound if tid != origin
                        and any(fx.spelled & names for fx in facts_by_target[tid])}
            # for the test-class pass: spread the names through downstream modules' declarations that use
            # them, so a test reached through an intermediate module is matched by the names it spells
            reach = set(names)
            while True:
                grown = set(reach)
                for tid in bound - {origin}:
                    if graph.targets[tid].is_test:
                        continue
                    facts = facts_by_target[tid]
                    using = {d.name for fx in facts for d in fx.decls if d.uses & grown}
                    if using - grown:
                        grown |= _propagate_within(using, facts, protocols)
                if grown == reach:
                    break
                reach = grown
            self.hints["names"] |= reach
            self.hints["spellers"] |= spellers | {tid for tid in bound if graph.targets[tid].is_test
                                                  and any(fx.spelled & reach for fx in facts_by_target[tid])}
            affected = graph.transitive_dependents(spellers)
            if self.own_tests_always:
                own = {tid for tid in bound if graph.targets[tid].is_test and origin in graph.targets[tid].deps
                       and graph.targets[tid].name == graph.targets[origin].name + "Tests"}
                affected |= own
            tests |= {tid for tid in affected if graph.targets[tid].is_test}

        return Selection(self.name, tests, rules=rules)


def names_of_decl(d, protocols: set[str]) -> set[str]:
    """Names a dependent must spell to be affected when declaration `d` changes."""
    names = set(d.name.split(","))
    if d.kind == "protocol" or (d.kind == "extension" and d.name in protocols):
        names.add(f"conformers-of:{d.name}")
    if d.owner:
        widen = (d.name in IMPLICIT_MEMBERS or d.stored or not _IDENT.match(d.name)
                 or d.kind in ("init", "deinit", "case", "subscript", "associatedtype"))
        if widen:
            names.add(d.owner)
        if d.owner_kind == "protocol" or (d.owner_kind == "extension" and d.owner in protocols):
            names.add(d.owner)
            names.add(f"conformers-of:{d.owner}")
    return names


def _propagate_within(names: set[str], facts: list[FileFacts], protocols: set[str], limit: int = 50) -> set[str]:
    """Inside the origin target, a declaration that uses a changed name has changed behaviour too.

    Repeat until nothing new is added, so an internal helper's change reaches the public API that
    dependents and tests actually spell.
    """
    names = set(names)
    for _ in range(limit):
        plain = {n for n in names if not n.startswith("conformers-of:")} | {
            n.split(":", 1)[1] for n in names if n.startswith("conformers-of:")}
        added = set()
        for fx in facts:
            for d in fx.decls:
                if (d.uses - {d.name}) & plain:
                    added |= names_of_decl(d, protocols) - names
        if not added:
            break
        names |= added
    return names


def _expand_conformers(names: set[str], conformances: dict[str, set[str]]) -> set[str]:
    """Replace `conformers-of:P` markers with every type that conforms to P, directly or through refinement."""
    markers = {n for n in names if n.startswith("conformers-of:")}
    out = names - markers
    frontier = {m.split(":", 1)[1] for m in markers}
    seen: set[str] = set()
    while frontier:
        p = frontier.pop()
        if p in seen:
            continue
        seen.add(p)
        out.add(p)
        for t, inh in conformances.items():
            if p in inh and t not in seen:
                frontier.add(t)
    return out
