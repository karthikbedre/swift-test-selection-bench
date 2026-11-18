"""Study run on one subject: real commits plus seeded mutants, all selectors, oracle per head."""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsel.changes import read_changes
from tsel.graph import load_graph
from tsel.mutate import candidates, make_mutant
from tsel.oracle import run_oracle
from tsel.replay import commits, manifests_at
from tsel.selectors import SELECTORS
from tsel.selectors.hash_cache import _has_bazel

repo, end, count, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
names = ["run-all", "package-graph", "tree-sitter", "compiler-index", "interface-only"]
if _has_bazel(repo, end):
    names.append("hash-cache")
insts = {n: SELECTORS[n]() for n in names}
wt = str(out / "oracle-worktree")
random.seed(7)
revs = commits(repo, end, count + 1)
done = set()
if (out / "selections.jsonl").exists():   # resume an interrupted run
    done = {json.loads(l)["head"] for l in open(out / "selections.jsonl") if '"kind": "real"' in l}
sel_fh = open(out / "selections.jsonl", "a")


def select(base, head, kind, meta):
    changes = read_changes(repo, base, head)
    graph = load_graph(repo, ["."], manifest_text=manifests_at(repo, head, ["."]))
    row = {"base": base, "head": head, "kind": kind, **meta, "files": [f.path for f in changes.files],
           "test_targets": len(graph.test_targets()), "selections": {}}
    for n, s in insts.items():
        row["selections"][n] = s.select(changes, graph).to_json()
    sel_fh.write(json.dumps(row) + "\n")
    sel_fh.flush()


for i, (base, head) in enumerate(zip(revs, revs[1:])):
    if head in done:
        continue
    t0 = time.time()
    select(base, head, "real", {})
    run_oracle(repo, head, str(out / "oracle.jsonl"), worktree=wt)
    cands = candidates(repo, base, head)
    random.shuffle(cands)
    picked, seen = [], set()
    for c in cands:
        if (c[0], c[1]) not in seen:
            picked.append(c)
            seen.add((c[0], c[1]))
        if len(picked) == 2:
            break
    for path, line, op, old, new in picked:
        m = make_mutant(repo, head, path, line, new, f"mutant {op} {path}:{line}")
        select(base, m, "mutant", {"of": head, "op": op, "path": path, "line": line})
        run_oracle(repo, m, str(out / "oracle.jsonl"), worktree=wt)
    print(f"{i+1}/{count} {head[:8]} mutants={len(picked)} {time.time()-t0:.0f}s", flush=True)
