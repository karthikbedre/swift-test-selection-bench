"""The compiler-index selector.

1. Check out the base revision in a scratch worktree and build it with tests and indexing on
   (``swift build --build-tests --enable-index-store``). That build is this selector's overhead. The
   worktree is kept between calls, so on a replay each build is incremental from the previous commit.
2. Sort the change exactly as the Tree-sitter selector does (same file routing, same trivia-only
   rule), then map changed lines to the declarations around them.
3. Ask ``tools/index-query`` (a small Swift tool on IndexStoreDB) which files refer to those
   declarations. Inside the changed module it follows references to the declarations that contain
   them, until nothing new is found, so a change to an internal helper reaches the public API.
4. A target with a referring file is affected, and so is every target that depends on it (the chain
   rule). The origin's own test target always runs. The answer is intersected with the package graph.

Falls back to the package graph for an origin when a changed declaration cannot be found in the
index, or sits under ``#if`` (the index only sees the built configuration). Known blind spots it
does not patch, because measuring them is part of the study: code the compiler synthesizes
(Codable, Equatable, Hashable, memberwise initializers) and calls the index does not record
(such as ``description`` reached through string interpolation).

Needs macOS or Linux with a Swift toolchain, and ``tools/index-query`` built once:
``swift build -c release --package-path tools/index-query``.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ..changes import ChangeSet, FileChange
from ..graph import Graph
from ..swiftdecl import innermost
from .base import Selection, Selector, route
from .treesitter import TreeSitterSelector

REPO_ROOT = Path(__file__).resolve().parents[2]


class IndexUnavailable(Exception):
    pass


def find_index_query() -> str:
    env = os.environ.get("TSEL_INDEX_QUERY")
    candidates = [env] if env else []
    candidates.append(str(REPO_ROOT / "tools" / "index-query" / ".build" / "release" / "index-query"))
    for c in candidates:
        if c and os.access(c, os.X_OK):
            return c
    raise IndexUnavailable("index-query is not built: swift build -c release --package-path tools/index-query")


def find_libindexstore() -> str:
    env = os.environ.get("TSEL_LIBINDEXSTORE")
    if env:
        return env
    swift = None
    if shutil.which("xcrun"):
        r = subprocess.run(["xcrun", "--find", "swift"], capture_output=True, text=True)
        swift = r.stdout.strip() or None
    swift = swift or shutil.which("swift")
    if not swift:
        raise IndexUnavailable("no Swift toolchain on PATH")
    usr = Path(os.path.realpath(swift)).parent.parent
    for name in ("libIndexStore.dylib", "libIndexStore.so"):
        p = usr / "lib" / name
        if p.exists():
            return str(p)
    raise IndexUnavailable(f"libIndexStore not found under {usr / 'lib'}; set TSEL_LIBINDEXSTORE")


class CompilerIndex(Selector):
    name = "compiler-index"

    def __init__(self, cache_dir: str | None = None, own_tests_always: bool = True):
        self.cache_dir = Path(cache_dir or os.environ.get("TSEL_CACHE", Path.home() / ".cache" / "tsel"))
        self.own_tests_always = own_tests_always
        self._facts = TreeSitterSelector._facts

    # -- index build ----------------------------------------------------------------------------
    def _ensure_index(self, changes: ChangeSet, graph: Graph) -> tuple[str, str, float]:
        """Return (worktree, index store dir, seconds spent building)."""
        # One worktree per repository, moved to each base in turn, so the build is incremental from the
        # previous commit: the warm-cache case a CI machine with a kept build folder would see.
        key = hashlib.sha1(os.path.realpath(changes.repo).encode()).hexdigest()[:16]
        wt = self.cache_dir / "worktrees" / key
        t0 = time.perf_counter()
        if not wt.exists():
            wt.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "-C", changes.repo, "worktree", "add", "--force", "--detach", str(wt), changes.base],
                           check=True, capture_output=True)
        else:
            subprocess.run(["git", "-C", str(wt), "checkout", "--force", "--detach", changes.base],
                           check=True, capture_output=True)
        for pkg in graph.packages:
            r = subprocess.run(["swift", "build", "--build-tests", "--enable-index-store"],
                               cwd=str(wt / pkg.dir), capture_output=True, text=True)
            if r.returncode != 0:
                raise IndexUnavailable(f"index build failed in {pkg.dir}: {r.stderr[-300:]}")
        stores = sorted(glob.glob(str(wt / "**" / ".build" / "**" / "index" / "store"), recursive=True))
        stores = stores or sorted(glob.glob(str(wt / ".build" / "**" / "index" / "store"), recursive=True))
        if not stores:
            raise IndexUnavailable("no index store found after the build")
        return str(wt), stores[0], time.perf_counter() - t0

    def _query(self, request: dict) -> dict:
        r = subprocess.run([find_index_query()], input=json.dumps(request), capture_output=True, text=True)
        if r.returncode != 0:
            raise IndexUnavailable(f"index-query failed: {r.stderr[-300:]}")
        return json.loads(r.stdout)

    # -- request building -----------------------------------------------------------------------
    def _request_items(self, changes: ChangeSet, f: FileChange, wt: str, rules: list[str]) -> tuple[list[dict], list[str]] | None:
        """Changed declarations of one file, located in the base worktree. None means nothing can fail."""
        old = self._facts(changes.repo, changes.base, f.old_path or f.path) if f.status != "A" else None
        new = self._facts(changes.repo, changes.head, f.path) if f.status != "D" else None
        if old is not None and new is not None and old.leaf_signature == new.leaf_signature:
            if old.line_sensitive or new.line_sensitive:
                raise _Fallback(f"line-sensitive:{f.path}")
            rules.append(f"trivia-only:{f.path}")
            return None
        if f.status in ("M", "R") and not (f.old_lines or f.new_lines):
            raise _Fallback(f"no-diff-ranges:{f.path}")

        base_path = os.path.realpath(os.path.join(wt, f.old_path or f.path))
        items: list[dict] = []
        added: list[str] = []
        if old is not None:
            ranges = [(d.start, d.end) for d in old.decls] if f.status == "D" else f.old_lines
            for a, b in ranges:
                hits = innermost(old.decls, a, b)
                if any(d.in_conditional for d in hits):
                    raise _Fallback(f"conditional-compilation:{f.path}:{a}")
                overlaps_error = any(ea <= b and eb >= a for ea, eb in old.error_lines)
                if not hits or overlaps_error:
                    items.append({"path": base_path, "startLine": a, "endLine": b, "mode": "nearest"})
                else:
                    for d in hits:
                        items.append({"path": base_path, "startLine": d.start, "endLine": d.end, "mode": "range"})
        if new is not None:
            old_keys = {d.key for d in old.decls} if old is not None else set()
            for d in new.decls:
                if d.key not in old_keys:
                    if d.in_conditional:
                        raise _Fallback(f"conditional-compilation:{f.path}:{d.start}")
                    added.extend(n for n in d.name.split(",") if n)
                    if d.owner:
                        added.append(d.owner)
        return items, added

    # -- selection ------------------------------------------------------------------------------
    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        r = route(changes, graph)
        if r.all_tests_reasons:
            return Selection(self.name, graph.test_targets(), all_tests=True, rules=r.all_tests_reasons)

        rules: list[str] = []
        tests: set[str] = set(r.test_targets)
        for origin, reasons in r.coarse_origins.items():
            rules.extend(f"fallback:{x}" for x in reasons)
            tests |= self.graph_tests(graph, {origin})
        if not r.source_changes:
            return Selection(self.name, tests, rules=rules)

        try:
            wt, store, build_secs = self._ensure_index(changes, graph)
        except IndexUnavailable as e:
            rules.append(f"fallback:index-unavailable:{e}")
            return Selection(self.name, tests | self.graph_tests(graph, set(r.source_changes)), rules=rules)
        rules.append(f"index-build-seconds:{build_secs:.1f}")
        wt_real = os.path.realpath(wt)

        for origin, files in r.source_changes.items():
            bound = graph.transitive_dependents({origin})
            try:
                items: list[dict] = []
                added: list[str] = []
                for f in files:
                    got = self._request_items(changes, f, wt, rules)
                    if got is not None:
                        items.extend(got[0])
                        added.extend(got[1])
                if not items and not added:
                    continue
                with tempfile.TemporaryDirectory() as dbdir:
                    resp = self._query({"store": store, "database": dbdir, "library": find_libindexstore(),
                                        "changes": items, "addedNames": sorted(set(added)), "maxDepth": 50})
                if resp.get("unresolved"):
                    u = resp["unresolved"][0]
                    raise _Fallback(f"not-in-index:{os.path.relpath(u['path'], wt_real)}:{u['startLine']}")
            except (_Fallback, IndexUnavailable) as fb:
                rules.append(f"fallback:{fb}")
                tests |= self.graph_tests(graph, {origin})
                continue

            referring: set[str] = set()
            for path in resp.get("files", {}):
                rel = os.path.relpath(os.path.realpath(path), wt_real)
                if rel.startswith(".."):
                    continue
                owner = graph.owner_of(rel)
                if owner is not None and owner in bound and owner != origin:
                    referring.add(owner)
            rules.append(f"index:{graph.targets[origin].name}:symbols={resp.get('visitedSymbols', 0)}"
                         f":targets={len(referring)}")
            affected = graph.transitive_dependents(referring)
            if self.own_tests_always:
                affected |= {tid for tid in bound if graph.targets[tid].is_test and origin in graph.targets[tid].deps
                             and graph.targets[tid].name == graph.targets[origin].name + "Tests"}
            tests |= {tid for tid in affected if graph.targets[tid].is_test}

        return Selection(self.name, tests, rules=rules)


class _Fallback(Exception):
    pass
