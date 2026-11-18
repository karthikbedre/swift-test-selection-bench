"""Hash-based selection through Bazel, using target-determinator.

Bazel hashes every target's inputs (sources, BUILD attributes, dependencies' hashes, toolchain). A test
target is selected when its hash differs between base and head. Files that are not inputs to any target
(CI configuration, scripts, docs, a Package.swift Bazel never reads) change no hash and select nothing.

target-determinator (https://github.com/bazel-contrib/target-determinator) does the hashing: it runs
`bazel cquery` at both revisions. It needs the head checked out, so the selector keeps one worktree per
repository under ~/.cache/tsel/hash-cache and moves it to each head in turn. The whole call, Bazel's
query time included, counts as the deciding overhead.

Only subjects with a Bazel build (MODULE.bazel or WORKSPACE at head) can use it. On others it selects
everything and records the rule `no-bazel-build`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from ..changes import ChangeSet
from ..graph import Graph
from .base import Selection, Selector


def find_target_determinator() -> str | None:
    env = os.environ.get("TSEL_TARGET_DETERMINATOR")
    if env:
        return env
    local = Path.home() / ".cache" / "tsel" / "bin" / "target-determinator"
    return str(local) if local.exists() else shutil.which("target-determinator")


def _has_bazel(repo: str, rev: str) -> bool:
    for name in ("MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel"):
        if subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{rev}:{name}"], capture_output=True).returncode == 0:
            return True
    return False


class HashCache(Selector):
    name = "hash-cache"

    def __init__(self, cache_dir: str | None = None, bazel: str | None = None):
        self.cache_dir = Path(cache_dir or os.environ.get("TSEL_CACHE", Path.home() / ".cache" / "tsel"))
        self.bazel = bazel or os.environ.get("TSEL_BAZEL") or shutil.which("bazelisk") or "bazel"

    def _worktree(self, repo: str, head: str) -> Path:
        key = hashlib.sha1(os.path.realpath(repo).encode()).hexdigest()[:16]
        wt = self.cache_dir / "hash-cache" / key
        if not wt.exists():
            wt.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "-C", repo, "worktree", "add", "--force", "--detach", str(wt), head],
                           check=True, capture_output=True)
        else:
            subprocess.run(["git", "-C", str(wt), "checkout", "--force", "--detach", head], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(wt), "clean", "-fdq"], check=True, capture_output=True)
        return wt

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        everything = graph.test_targets()
        if not _has_bazel(changes.repo, changes.head):
            return Selection(self.name, everything, all_tests=True, rules=["no-bazel-build"])
        td = find_target_determinator()
        if td is None:
            return Selection(self.name, everything, all_tests=True, rules=["no-target-determinator"])
        wt = self._worktree(changes.repo, changes.head)
        r = subprocess.run([td, f"-bazel={self.bazel}", "-nocache_results", "-targets", 'kind(".*_test", //...)',
                            changes.base], cwd=str(wt), capture_output=True, text=True)
        if r.returncode != 0:
            return Selection(self.name, everything, all_tests=True,
                             rules=[f"target-determinator-failed:{r.stderr.strip().splitlines()[-1][:200] if r.stderr.strip() else r.returncode}"])
        labels = [l.strip() for l in r.stdout.splitlines() if l.startswith("//")]
        by_name = {graph.targets[t].name: t for t in everything}
        tests, unmapped = set(), []
        for label in labels:
            name = label.rsplit(":", 1)[-1]
            if name in by_name:
                tests.add(by_name[name])
            else:
                unmapped.append(label)
        rules = [f"bazel-affected:{len(labels)}"] + [f"unmapped:{u}" for u in unmapped]
        return Selection(self.name, tests, rules=rules)
