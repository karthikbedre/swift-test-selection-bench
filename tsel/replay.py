"""Replay a subject's history and record what each selector would choose for every commit.

Selection never needs a checkout: files and manifests are read from git at each revision,
so a few hundred commits replay in minutes on any machine. Running the tests is separate
(see oracle.py) and needs the subject's toolchain.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .changes import read_changes
from .graph import load_graph
from .selectors import SELECTORS


def commits(repo: str, end: str, count: int) -> list[str]:
    """The last `count` first-parent commits ending at `end`, oldest first."""
    out = subprocess.run(["git", "-C", repo, "rev-list", "--first-parent", f"--max-count={count}", end],
                         check=True, capture_output=True, text=True).stdout.split()
    return list(reversed(out))


def manifests_at(repo: str, rev: str, package_dirs: list[str]) -> dict[str, str]:
    out = {}
    for d in package_dirs:
        p = "Package.swift" if d == "." else f"{d}/Package.swift"
        r = subprocess.run(["git", "-C", repo, "show", f"{rev}:{p}"], capture_output=True, text=True)
        if r.returncode == 0:
            out[d] = r.stdout
    return out


def replay(repo: str, end: str, count: int, selectors: list[str], out_path: str,
           package_dirs: list[str] | None = None) -> int:
    package_dirs = package_dirs or ["."]
    revs = commits(repo, end, count + 1)
    insts = {name: SELECTORS[name]() for name in selectors}
    n = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        for base, head in zip(revs, revs[1:]):
            changes = read_changes(repo, base, head)
            graph = load_graph(repo, package_dirs, manifest_text=manifests_at(repo, head, package_dirs))
            row = {"base": base, "head": head, "files": [f.path for f in changes.files],
                   "test_targets": len(graph.test_targets()), "graph_approximate": graph.approximate,
                   "selections": {}}
            for name, sel in insts.items():
                try:
                    row["selections"][name] = sel.select(changes, graph).to_json()
                except NotImplementedError as e:
                    row["selections"][name] = {"error": str(e)}
            fh.write(json.dumps(row) + "\n")
            n += 1
    return n
