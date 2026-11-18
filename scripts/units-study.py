#!/usr/bin/env python3
"""The test-class pass on a finished target-level run.

    scripts/units-study.py <subject repo> <target-level results dir> <out dir> [max commits]

Takes the commits and seeded bugs where the package graph did not run everything, reruns every selector
the run used, maps their evidence to test classes (tsel/units.py), and runs the oracle with per-class
results. With `max commits`, takes that many qualifying commits spread evenly over the history, with
their seeded bugs. Resumes if rerun. Writes units-selections.jsonl and units-oracle.jsonl.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsel.changes import read_changes
from tsel.graph import load_graph
from tsel.oracle import run_oracle
from tsel.replay import manifests_at
from tsel.selectors import SELECTORS
from tsel.units import TargetUnits, select_units, target_units

repo, src, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
cap = int(sys.argv[4]) if len(sys.argv) > 4 else 0
out.mkdir(parents=True, exist_ok=True)
rows = [json.loads(l) for l in open(src / "selections.jsonl")]
names = [n for n in ["run-all", "package-graph", "tree-sitter", "compiler-index", "interface-only", "hash-cache"]
         if n in rows[0]["selections"]]


def qualifies(r: dict) -> bool:
    g = r["selections"]["package-graph"]
    return not g["all_tests"] and bool(g["tests"])


reals = [r for r in rows if r["kind"] == "real" and qualifies(r)]
if cap and len(reals) > cap:
    step = len(reals) / cap
    reals = [reals[int(i * step)] for i in range(cap)]
chosen_heads = {r["head"] for r in reals}
plan = [r for r in rows if (r["kind"] == "real" and r["head"] in chosen_heads)
        or (r["kind"] == "mutant" and r["of"] in chosen_heads and qualifies(r))]

done = set()
if (out / "units-oracle.jsonl").exists():
    done = {json.loads(l)["rev"] for l in open(out / "units-oracle.jsonl")}
insts = {n: (SELECTORS[n](across_modules=True) if n == "compiler-index" else SELECTORS[n]()) for n in names}
cache: dict[tuple[str, str], TargetUnits] = {}
print(f"{len(reals)} commits and {len(plan) - len(reals)} seeded bugs to run; {len(done)} already done", flush=True)

with open(out / "units-selections.jsonl", "a") as fh:
    for i, r in enumerate(plan):
        if r["head"] in done:
            continue
        t0 = time.time()
        changes = read_changes(repo, r["base"], r["head"])
        graph = load_graph(repo, ["."], manifest_text=manifests_at(repo, r["head"], ["."]))
        units_of: dict[str, TargetUnits] = {}
        for tid in graph.test_targets():
            tree = subprocess.run(["git", "-C", repo, "rev-parse", f"{r['head']}:{graph.targets[tid].path}"],
                                  capture_output=True, text=True).stdout.strip()
            key = (tid, tree)
            if key not in cache:
                cache[key] = target_units(repo, r["head"], graph, tid)
            units_of[tid] = cache[key]
        row = {"head": r["head"], "base": r["base"], "kind": r["kind"], "of": r.get("of"),
               "units_total": {t: sorted(u.units) for t, u in units_of.items()}, "selections": {}}
        for n, s in insts.items():
            sel = s.select(changes, graph)
            hints = getattr(s, "hints", None) if n in ("tree-sitter", "compiler-index") else None
            picked, whole = select_units(n, sel.tests, hints, graph, units_of)
            row["selections"][n] = {"targets": sorted(sel.tests), "seconds": round(sel.seconds, 3),
                                    "units": {t: sorted(u) for t, u in sorted(picked.items())},
                                    "whole": sorted(whole), "rules": sel.rules}
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        run_oracle(repo, r["head"], str(out / "units-oracle.jsonl"), worktree=str(out / "oracle-worktree"), units=True)
        print(f"{i + 1}/{len(plan)} {r['kind']} {r['head'][:8]} {time.time() - t0:.0f}s", flush=True)
