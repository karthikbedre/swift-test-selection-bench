import json
import re
import sys
from collections import defaultdict

out = sys.argv[1]
sels = [json.loads(l) for l in open(f"{out}/selections.jsonl")]
orc = {}
for l in open(f"{out}/oracle.jsonl"):
    r = json.loads(l)
    orc[r["rev"]] = r


def failing(rev):
    o = orc.get(rev)
    if not o:
        return None
    return {t for t, e in o["targets"].items() if e["code"] != 0 and not e.get("flaky")}


names = ["run-all", "package-graph", "tree-sitter", "compiler-index"]
stat = {n: defaultdict(float) for n in names}
mut_rows = []
zero = set()
for row in sels:
    o = orc.get(row["head"])
    if not o or any(b["code"] != 0 for b in o["build"].values()):
        if row["kind"] == "mutant":
            mut_rows.append((row, "no-build"))
        continue
    for t, e in o["targets"].items():
        if e.get("zero_tests"):
            zero.add(t.split("::")[1])
    fails = failing(row["head"])
    if row["kind"] == "mutant":
        base_fail = failing(row["of"]) or set()
        killers = fails - base_fail
        mut_rows.append((row, "killed" if killers else "survived"))
        if not killers:
            continue
        for n in names:
            chosen = set(row["selections"][n]["tests"])
            s = stat[n]
            s["mutants_killed"] += 1
            if not (killers & chosen):
                s["mutants_missed"] += 1
                s.setdefault("missed_list", [])
                stat[n]["missed_list"].append(f"{row['op']} {row['path']}:{row['line']} killers={sorted(k.split('::')[1] for k in killers)}")
        continue
    all_secs = sum(e["seconds"] for e in o["targets"].values())
    for n in names:
        sel = row["selections"][n]
        chosen = set(sel["tests"])
        s = stat[n]
        s["commits"] += 1
        s["share"] += len(chosen) / max(len(o["targets"]), 1)
        s["test_secs"] += sum(o["targets"][t]["seconds"] for t in chosen if t in o["targets"])
        m = [float(x.split(":")[1]) for x in sel["rules"] if x.startswith("index-build-seconds:")]
        s["overhead"] += (m[0] if m else 0) + sel["seconds"] * (0 if m else 1)
        s["all_secs"] += all_secs
        s["real_missed"] += 1 if fails - chosen else 0
        s["fallbacks"] += 1 if any(r.startswith("fallback") for r in sel["rules"]) else 0
        s["empty"] += 1 if not chosen else 0

print("real commits / mutants:", sum(1 for r in sels if r["kind"] == "real"),
      {k: sum(1 for _, v in mut_rows if v == k) for k in ("killed", "survived", "no-build")})
print("zero-test targets:", sorted(zero))
for n in names:
    s = stat[n]
    c = s["commits"] or 1
    print(f"{n:15} commits={int(s['commits'])} share={s['share']/c:.2f} empty={int(s['empty'])} "
          f"test_s={s['test_secs']:.0f}/{s['all_secs']:.0f} overhead_s={s['overhead']:.0f} "
          f"fallback_commits={int(s['fallbacks'])} real_missed={int(s['real_missed'])} "
          f"mutants_missed={int(s['mutants_missed'])}/{int(s['mutants_killed'])}")
    for x in s.get("missed_list", []):
        print("    missed:", x)
