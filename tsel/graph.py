"""The package graph: targets, what they depend on, and which files they own.

Two loaders build the same graph:

* ``swift package dump-package`` (exact; needs a Swift toolchain), used when ``swift`` is on PATH.
* A Tree-sitter reader of ``Package.swift`` (approximate; no toolchain), used otherwise.
  It understands literal ``.target(...)`` calls, string and ``.target``/``.product`` dependencies,
  and ``let`` constants holding those. Manifests that build targets in loops or helper
  functions need the toolchain loader; ``Graph.approximate`` is set so results can be flagged.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

DEFAULT_DIRS = {"regular": "Sources", "executable": "Sources", "macro": "Sources", "system": "Sources",
                "binary": "Sources", "test": "Tests", "plugin": "Plugins"}


@dataclass
class Target:
    id: str              # unique across the repo: "<package dir>::<name>" ("." for the root package)
    name: str
    package_dir: str     # relative to repo root, "." for root
    kind: str            # regular | test | executable | macro | plugin | system | binary
    path: str            # directory relative to repo root
    dep_refs: list[tuple[str, str | None]] = field(default_factory=list)  # (kind, name) unresolved
    deps: set[str] = field(default_factory=set)                           # resolved target ids

    @property
    def is_test(self) -> bool:
        return self.kind == "test"


@dataclass
class Package:
    dir: str
    name: str
    targets: dict[str, Target]                 # by target name
    products: dict[str, list[str]]             # product name -> target names
    approximate: bool = False


class Graph:
    def __init__(self, repo: str, packages: list[Package]):
        self.repo = repo
        self.packages = packages
        self.targets: dict[str, Target] = {t.id: t for p in packages for t in p.targets.values()}
        self.approximate = any(p.approximate for p in packages)
        self._resolve()
        self.dependents: dict[str, set[str]] = {tid: set() for tid in self.targets}
        for t in self.targets.values():
            for d in t.deps:
                self.dependents.setdefault(d, set()).add(t.id)

    # -- construction -------------------------------------------------------------------------
    def _resolve(self) -> None:
        products: dict[str, list[str]] = {}
        for p in self.packages:
            for prod, names in p.products.items():
                products.setdefault(prod, []).extend(p.targets[n].id for n in names if n in p.targets)
        for p in self.packages:
            for t in p.targets.values():
                for kind, name in t.dep_refs:
                    if not name:
                        continue
                    if kind in ("byName", "target") and name in p.targets:
                        t.deps.add(p.targets[name].id)
                    elif kind in ("byName", "product") and name in products:
                        t.deps.update(products[name])
                    # anything else is an external package: outside the repo, never changes here

    # -- queries ------------------------------------------------------------------------------
    def test_targets(self) -> set[str]:
        return {tid for tid, t in self.targets.items() if t.is_test}

    def owner_of(self, path: str) -> str | None:
        """The target whose directory holds `path` (longest prefix wins)."""
        best, best_len = None, -1
        p = PurePosixPath(path)
        for t in self.targets.values():
            tp = PurePosixPath(t.path)
            if tp == p or tp in p.parents:
                n = len(tp.parts)
                if n > best_len:
                    best, best_len = t.id, n
        return best

    def package_of(self, path: str) -> Package | None:
        best, best_len = None, -1
        p = PurePosixPath(path)
        for pkg in self.packages:
            d = PurePosixPath(pkg.dir)
            if pkg.dir == "." or d in p.parents:
                n = 0 if pkg.dir == "." else len(d.parts)
                if n > best_len:
                    best, best_len = pkg, n
        return best

    def transitive_dependents(self, seeds: set[str], include_seeds: bool = True) -> set[str]:
        out = set(seeds) if include_seeds else set()
        queue = deque(seeds)
        while queue:
            cur = queue.popleft()
            for d in self.dependents.get(cur, ()):
                if d not in out:
                    out.add(d)
                    queue.append(d)
        return out

    def transitive_deps(self, tid: str) -> set[str]:
        out: set[str] = set()
        queue = deque([tid])
        while queue:
            cur = queue.popleft()
            for d in self.targets[cur].deps:
                if d not in out:
                    out.add(d)
                    queue.append(d)
        return out

    def describe(self) -> dict:
        return {tid: {"kind": t.kind, "path": t.path, "deps": sorted(t.deps)} for tid, t in sorted(self.targets.items())}


# -- loaders ----------------------------------------------------------------------------------

def _target_id(pkg_dir: str, name: str) -> str:
    return f"{pkg_dir}::{name}"


def _join(pkg_dir: str, sub: str) -> str:
    return sub if pkg_dir == "." else str(PurePosixPath(pkg_dir) / sub)


def package_from_dump(dump: dict, pkg_dir: str) -> Package:
    targets: dict[str, Target] = {}
    for t in dump.get("targets", []):
        kind = t.get("type", "regular")
        sub = t.get("path") or f"{DEFAULT_DIRS.get(kind, 'Sources')}/{t['name']}"
        refs: list[tuple[str, str | None]] = []
        for d in t.get("dependencies", []):
            for key in ("byName", "target", "product"):
                if key in d:
                    refs.append((key, d[key][0]))
        targets[t["name"]] = Target(id=_target_id(pkg_dir, t["name"]), name=t["name"], package_dir=pkg_dir,
                                    kind=kind, path=_join(pkg_dir, sub), dep_refs=refs)
    products = {p["name"]: list(p.get("targets", [])) for p in dump.get("products", [])}
    return Package(dir=pkg_dir, name=dump.get("name", pkg_dir), targets=targets, products=products)


def _dump_with_toolchain(repo: str, pkg_dir: str) -> dict | None:
    swift = shutil.which("swift")
    if not swift:
        return None
    try:
        out = subprocess.run([swift, "package", "--package-path", str(Path(repo) / pkg_dir), "dump-package"],
                             check=True, capture_output=True, text=True, timeout=600).stdout
        return json.loads(out)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def load_graph(repo: str, package_dirs: list[str] | None = None, prefer_toolchain: bool = True,
               manifest_text: dict[str, str] | None = None) -> Graph:
    """Load every listed package (default: the root package only).

    `manifest_text` lets callers supply manifests for a revision that is not checked out
    (the replay harness reads Package.swift from git), which forces the Tree-sitter loader.
    """
    from .manifest import package_from_manifest  # local import keeps tree-sitter optional for dump users

    package_dirs = package_dirs or ["."]
    packages = []
    for pkg_dir in package_dirs:
        dump = None
        if prefer_toolchain and manifest_text is None:
            dump = _dump_with_toolchain(repo, pkg_dir)
        if dump is not None:
            packages.append(package_from_dump(dump, pkg_dir))
            continue
        if manifest_text is not None and pkg_dir in manifest_text:
            text = manifest_text[pkg_dir]
        else:
            text = (Path(repo) / pkg_dir / "Package.swift").read_text()
        packages.append(package_from_manifest(text, pkg_dir))
    return Graph(repo, packages)
