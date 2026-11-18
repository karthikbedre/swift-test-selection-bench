"""Interface-only: a deliberately unsafe variant that states a common intuition as a rule.

The intuition: only a change to a module's public interface can affect the modules that import it.
So a Swift edit selects the owning target's closest tests, and reaches dependents' tests only when the
file's public interface changed: a `public` or `open` declaration was added, removed, or had its header
(name, parameters, types, modifiers) changed. Bodies, initial values, private and internal declarations
never reach dependents. Everything else (manifests, resources, unowned files) is routed as the package
graph routes it.

Its missed seeded bugs measure what the intuition costs.
"""
from __future__ import annotations

import subprocess

from ..changes import ChangeSet, FileChange
from ..graph import Graph
from ..ts import parse, text, walk
from .base import Selection, Selector, route

DECLS = {
    "function_declaration", "property_declaration", "init_declaration", "subscript_declaration",
    "typealias_declaration", "class_declaration", "protocol_declaration", "protocol_function_declaration",
    "protocol_property_declaration", "associatedtype_declaration", "enum_entry",
}
BODIES = {"function_body", "computed_property", "class_body", "enum_class_body", "protocol_body"}


def _is_public(node) -> bool:
    mods = next((c for c in node.children if c.type == "modifiers"), None)
    if mods is not None and any(text(m) in ("public", "open") for m in walk(mods)):
        return True
    # members of a public protocol and cases of a public enum are public without saying so
    parent = node.parent
    while parent is not None and parent.type not in DECLS:
        parent = parent.parent
    if parent is not None and node.type in ("protocol_function_declaration", "protocol_property_declaration",
                                            "associatedtype_declaration", "enum_entry"):
        return _is_public(parent)
    return False


def _header(node) -> str:
    """The declaration without its body or initial value, whitespace-normalised."""
    parts, after_eq = [], False
    for c in node.children:
        if c.type in BODIES or after_eq:
            continue
        if c.type == "=" and node.type == "property_declaration":
            after_eq = True
            continue
        if c.type == "modifiers":
            parts.append(" ".join(text(m) for m in c.children if not text(m).startswith("//")))
            continue
        parts.append(text(c))
    return " ".join(" ".join(parts).split())


def public_interface(src: bytes) -> set[str]:
    out = set()
    for n in walk(parse(src).root_node):
        if n.type in DECLS and _is_public(n):
            out.add(f"{n.type}:{_header(n)}")
    return out


def _source(repo: str, rev: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def closest_tests(graph: Graph, origin: str) -> set[str]:
    """Test targets reaching `origin` only directly, not through another regular target that depends on it."""
    reach = graph.transitive_dependents({origin}, include_seeds=False)
    out = set()
    for t in reach:
        if not graph.targets[t].is_test:
            continue
        via = [d for d in graph.targets[t].deps if d != origin and d in reach]
        if origin in graph.targets[t].deps and not via:
            out.add(t)
    return out


class InterfaceOnly(Selector):
    name = "interface-only"

    def _interface_changed(self, changes: ChangeSet, f: FileChange) -> bool:
        old = _source(changes.repo, changes.base, f.old_path or f.path) if f.status != "A" else None
        new = _source(changes.repo, changes.head, f.path) if f.status != "D" else None
        before = public_interface(old) if old is not None else set()
        after = public_interface(new) if new is not None else set()
        return before != after

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        r = route(changes, graph)
        if r.all_tests_reasons:
            return Selection(self.name, graph.test_targets(), all_tests=True, rules=r.all_tests_reasons)
        tests = set(r.test_targets)
        rules: list[str] = []
        for origin in r.coarse_origins:
            tests |= self.graph_tests(graph, {origin})
            rules.append(f"graph:{origin}")
        for origin, files in r.source_changes.items():
            if any(self._interface_changed(changes, f) for f in files):
                tests |= self.graph_tests(graph, {origin})
                rules.append(f"interface:{origin}")
            else:
                tests |= closest_tests(graph, origin)
                rules.append(f"implementation:{origin}")
        return Selection(self.name, tests, rules=rules)
