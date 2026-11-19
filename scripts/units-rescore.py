#!/usr/bin/env python3
"""Apply a test-class rule added after a class pass ran, without rerunning it.

    scripts/units-rescore.py <subject repo> <target-level results dir> <units dir>

Rule applied: a test target with a changed file that is not Swift (a snapshot, fixture or resource) keeps
all its classes for every selector, because no selector can tell which class reads the file. For such a
target the rule decides the outcome whatever the other evidence, so applying it to stored rows gives what
the fixed code gives. Changed files come from the target-level run. The old file is kept as .bak.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsel.graph import load_graph
from tsel.replay import manifests_at

repo, src, d = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
files = {}
for l in open(src / "selections.jsonl"):
    r = json.loads(l)
    files[r["head"]] = r["files"]
path = d / "units-selections.jsonl"
shutil.copy(path, path.with_suffix(".jsonl.bak"))
rows, changed = [json.loads(l) for l in open(path)], 0
for r in rows:
    nonswift = [f for f in files.get(r["head"], []) if not f.endswith(".swift")]
    if not nonswift:
        continue
    graph = load_graph(repo, ["."], manifest_text=manifests_at(repo, r["head"], ["."]))
    owners = {graph.owner_of(f) for f in nonswift}
    for n, sel in r["selections"].items():
        for tid in sel["targets"]:
            if tid in owners and graph.targets[tid].is_test:
                every = r["units_total"].get(tid, [])
                if sel["units"].get(tid) != every:
                    sel["units"][tid] = every
                    changed += 1
                if n in ("tree-sitter", "compiler-index") and tid not in sel["whole"]:
                    sel["whole"] = sorted(set(sel["whole"]) | {tid})
path.write_text("".join(json.dumps(r) + "\n" for r in rows))
print(f"{path}: {changed} target selections widened to all classes")
