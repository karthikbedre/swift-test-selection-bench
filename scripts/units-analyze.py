#!/usr/bin/env python3
"""Score the test-class pass.

    scripts/units-analyze.py <units dir> [<units dir> ...]

Per subject and selector, over commits and seeded bugs the class oracle ran:
- share of test classes selected (of every class in every test target),
- test time of the selected classes (from per-class times),
- the same two at target level, for comparison,
- seeded bugs missed at class level (a bug's killers are the classes that fail with it and pass without),
- how often a selected target had to be kept whole.
Prints Markdown.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

SHORT = {"run-all": "all", "package-graph": "graph", "tree-sitter": "tree-sitter", "compiler-index": "index",
         "interface-only": "interface-only", "hash-cache": "Bazel hash"}


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path)] if path.exists() else []


def failing_units(o: dict) -> set[tuple[str, str]]:
    out = set()
    for t, e in o["targets"].items():
        if e.get("flaky"):
            continue
        for u, r in e.get("units", {}).items():
            if r["failed"]:
                out.add((t, u))
        if e["code"] != 0 and not e.get("units"):
            out.add((t, "*"))            # failed before reporting any test: the whole target
    return out


def report(d: Path) -> list[str]:
    sels = {}
    for r in load(d / "units-selections.jsonl"):
        sels[r["head"]] = r                       # last row wins after a resumed run
    orc = {r["rev"]: r for r in load(d / "units-oracle.jsonl")}
    names = next(iter(sels.values()))["selections"].keys() if sels else []
    stat = {n: defaultdict(float) for n in names}
    commits = muts = 0
    for head, r in sels.items():
        o = orc.get(head)
        if not o or any(b["code"] != 0 for b in o["build"].values()):
            continue
        unit_secs = {(t, u): v["seconds"] for t, e in o["targets"].items() for u, v in e.get("units", {}).items()}
        all_units = set(unit_secs)
        if r["kind"] == "mutant":
            base = orc.get(r["of"])
            killers = failing_units(o) - (failing_units(base) if base else set())
            if not killers:
                continue
            muts += 1
            for n in names:
                sel = r["selections"][n]
                chosen = {(t, u) for t, us in sel["units"].items() for u in us} | {(t, "*") for t in sel["targets"]}
                stat[n]["missed"] += 0 if killers & chosen else 1
            continue
        commits += 1
        target_secs = {t: e["seconds"] for t, e in o["targets"].items()}
        for n in names:
            sel = r["selections"][n]
            chosen = {(t, u) for t, us in sel["units"].items() for u in us} & all_units
            s = stat[n]
            s["unit_share"] += len(chosen) / max(len(all_units), 1)
            s["unit_secs"] += sum(unit_secs[c] for c in chosen)
            s["all_unit_secs"] += sum(unit_secs.values())
            s["target_share"] += len(sel["targets"]) / max(len(o["targets"]), 1)
            s["target_secs"] += sum(target_secs.get(t, 0) for t in sel["targets"])
            s["all_target_secs"] += sum(target_secs.values())
            s["selected_targets"] += len(sel["targets"])
            s["whole"] += len(sel["whole"])
    out = [f"### {d.name}", "", f"{commits} commits and {muts} caught seeded bugs with per-class results.", "",
           "| Selector | Share of targets | Share of classes | Class test time selected | Targets kept whole | Seeded bugs missed |",
           "|---|---|---|---|---|---|"]
    for n in names:
        s, c = stat[n], max(commits, 1)
        whole = f"{int(s['whole'])} of {int(s['selected_targets'])}" if n in ("tree-sitter", "compiler-index") else "-"
        out.append(f"| {SHORT[n]} | {s['target_share'] / c:.2f} | {s['unit_share'] / c:.2f} | "
                   f"{s['unit_secs']:.1f} of {s['all_unit_secs']:.1f} s | {whole} | {int(s['missed'])} of {muts} |")
    return out + [""]


if __name__ == "__main__":
    lines = ["## Test-class pass", ""]
    for p in sys.argv[1:]:
        lines += report(Path(p))
    print("\n".join(lines))
