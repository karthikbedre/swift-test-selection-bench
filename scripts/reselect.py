#!/usr/bin/env python3
"""Recompute every selection in a run with the current harness, keeping the oracle rows.

    scripts/reselect.py <subject repo> <results dir> [selector ...]

For use after a selector or harness fix. Rows are recomputed in their original order, so the compiler
index's kept worktree builds incrementally as it did in the run. The old file is kept as
selections.jsonl.bak. Seeded-bug commits are read from the subject repository, where the run created them.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsel.changes import read_changes
from tsel.graph import load_graph
from tsel.replay import manifests_at
from tsel.selectors import SELECTORS
from tsel.selectors.hash_cache import _has_bazel

repo, out = sys.argv[1], Path(sys.argv[2])
rows = [json.loads(l) for l in open(out / "selections.jsonl")]
names = sys.argv[3:] or ["run-all", "package-graph", "tree-sitter", "compiler-index", "interface-only"] + (
    ["hash-cache"] if _has_bazel(repo, rows[-1]["head"]) else [])
insts = {n: SELECTORS[n]() for n in names}
shutil.copy(out / "selections.jsonl", out / "selections.jsonl.bak")
tmp = out / "selections.jsonl.new"
with open(tmp, "w") as fh:
    for i, row in enumerate(rows):
        changes = read_changes(repo, row["base"], row["head"])
        graph = load_graph(repo, ["."], manifest_text=manifests_at(repo, row["head"], ["."]))
        row["files"] = [f.path for f in changes.files]
        row["test_targets"] = len(graph.test_targets())
        for n, s in insts.items():
            row["selections"][n] = s.select(changes, graph).to_json()
        fh.write(json.dumps(row) + "\n")
        if (i + 1) % 25 == 0:
            print(f"reselected {i + 1}/{len(rows)}", flush=True)
tmp.replace(out / "selections.jsonl")
print(f"reselected {len(rows)} rows with {', '.join(names)}")
