"""What every selector shares: the result type and the routing of changed files to targets."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..changes import ChangeSet, FileChange, FileClass
from ..graph import Graph


@dataclass
class Selection:
    selector: str
    tests: set[str]                                   # selected test target ids
    all_tests: bool = False
    rules: list[str] = field(default_factory=list)    # every rule or fallback that fired, for the fallback-rate metric
    seconds: float = 0.0

    def to_json(self) -> dict:
        return {"selector": self.selector, "tests": sorted(self.tests), "all_tests": self.all_tests,
                "rules": self.rules, "seconds": round(self.seconds, 4)}


@dataclass
class Routed:
    """Changed files sorted by what they mean for selection."""
    all_tests_reasons: list[str] = field(default_factory=list)
    test_targets: set[str] = field(default_factory=set)              # changed test files -> their own target
    source_changes: dict[str, list[FileChange]] = field(default_factory=dict)   # origin target -> Swift changes
    coarse_origins: dict[str, list[str]] = field(default_factory=dict)          # origin target -> non-Swift reasons
    ignored: list[str] = field(default_factory=list)


def _separate_package_root(repo: str, rev: str, path: str) -> str | None:
    """If `path` sits in a nested package that the graph did not load (e.g. Benchmarks/), return its dir."""
    parts = PurePosixPath(path).parts[:-1]
    for i in range(len(parts), 0, -1):
        d = "/".join(parts[:i])
        r = subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{rev}:{d}/Package.swift"], capture_output=True)
        if r.returncode == 0:
            return d
    return None


def route(changes: ChangeSet, graph: Graph) -> Routed:
    out = Routed()
    loaded_dirs = {p.dir for p in graph.packages}
    for f in changes.files:
        cls = f.file_class
        if cls == FileClass.DOCS:
            out.ignored.append(f.path)
            continue
        if cls in (FileClass.MANIFEST, FileClass.BUILD_SETTING):
            out.all_tests_reasons.append(f"{cls.value}:{f.path}")
            continue
        paths = [f.path] + ([f.old_path] if f.old_path else [])
        owners = {graph.owner_of(p) for p in paths}
        owners.discard(None)
        if not owners:
            nested = _separate_package_root(changes.repo, changes.head, f.path) or (
                _separate_package_root(changes.repo, changes.base, f.old_path or f.path))
            if nested is not None and nested not in loaded_dirs:
                out.ignored.append(f"{f.path} (separate package {nested})")
            else:
                out.all_tests_reasons.append(f"unowned:{f.path}")
            continue
        for owner in owners:
            t = graph.targets[owner]
            if t.is_test:
                out.test_targets.add(owner)
            elif cls == FileClass.SWIFT_SOURCE:
                out.source_changes.setdefault(owner, []).append(f)
            else:
                out.coarse_origins.setdefault(owner, []).append(f"{cls.value}:{f.path}")
    return out


class Selector:
    name = "base"

    def select(self, changes: ChangeSet, graph: Graph) -> Selection:
        t0 = time.perf_counter()
        sel = self._select(changes, graph)
        sel.seconds = time.perf_counter() - t0
        return sel

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:  # pragma: no cover
        raise NotImplementedError

    @staticmethod
    def graph_tests(graph: Graph, origins: set[str]) -> set[str]:
        return {t for t in graph.transitive_dependents(origins) if graph.targets[t].is_test}
