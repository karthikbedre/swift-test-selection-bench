#!/usr/bin/env python3
"""Write a Markdown report of every run under a results folder.

    scripts/report.py results/macos > results/macos/REPORT.md

Sections: per-subject summary (share selected, test time, deciding time, misses), commits that select
everything and why (H5), the compiler index's cost split into build and query (H4), the Civitas edit
catalogue (H1, H2, H2b, H7, H8), rebuild versus rerun (H3) and traps (H9). Each section is skipped when
its data is missing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ORDER = ["run-all", "package-graph", "tree-sitter", "compiler-index", "interface-only", "hash-cache"]
SHORT = {"run-all": "all", "package-graph": "graph", "tree-sitter": "tree-sitter", "compiler-index": "index",
         "interface-only": "interface-only", "hash-cache": "Bazel hash"}


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path)] if path.exists() else []


def failing(o: dict | None) -> set[str] | None:
    if o is None:
        return None
    return {t for t, e in o["targets"].items() if e["code"] != 0 and not e.get("flaky")}


def index_split(sel: dict) -> tuple[float, float]:
    """(build seconds, everything else) for one selection."""
    m = [float(x.split(":", 1)[1]) for x in sel["rules"] if x.startswith("index-build-seconds:")]
    build = m[0] if m else 0.0
    return build, max(sel["seconds"] - build, 0.0)


class Run:
    def __init__(self, d: Path):
        self.dir, self.name = d, d.name
        self.sels = load(d / "selections.jsonl")
        self.orc = {r["rev"]: r for r in load(d / "oracle.jsonl")}
        self.machine = json.loads((d / "machine.json").read_text()) if (d / "machine.json").exists() else {}
        self.names = [n for n in ORDER if any(n in s["selections"] for s in self.sels)]

    def built(self, rev: str) -> dict | None:
        o = self.orc.get(rev)
        return o if o and all(b["code"] == 0 for b in o["build"].values()) else None

    def reals(self):
        for r in self.sels:
            if r["kind"] == "real" and self.built(r["head"]):
                yield r, self.orc[r["head"]]

    def mutants(self):
        """(row, killer targets) for every seeded bug some test caught."""
        for r in self.sels:
            if r["kind"] != "mutant":
                continue
            o = self.built(r["head"])
            if not o:
                continue
            killers = failing(o) - (failing(self.orc.get(r["of"])) or set())
            if killers:
                yield r, killers


def summary(run: Run) -> list[str]:
    out = [f"### {run.name}", ""]
    m = run.machine
    if m:
        out.append(f"{m.get('cpu', '')}, {m.get('memory_gb', '')} GB, {m.get('os', '')}, {m.get('xcode', '')}, "
                   f"Swift {m.get('swift', '').split('Swift version ')[-1].split(' ')[0]}. Harness `{m.get('harness_commit', '')[:10]}`.")
        out.append("")
    reals = list(run.reals())
    muts = list(run.mutants())
    n_mut = sum(1 for r in run.sels if r["kind"] == "mutant")
    out.append(f"{len(reals)} commits built and tested; {n_mut} seeded bugs, {len(muts)} caught by at least one test.")
    out.append("")
    out.append("| Selector | Mean share of test targets | Test time selected | Deciding time | Selects everything | Falls back | Seeded bugs missed |")
    out.append("|---|---|---|---|---|---|---|")
    for n in run.names:
        share = secs = allsecs = decide = everything = fb = 0.0
        for r, o in reals:
            sel = r["selections"][n]
            chosen = set(sel["tests"])
            share += len(chosen) / max(len(o["targets"]), 1)
            secs += sum(o["targets"][t]["seconds"] for t in chosen if t in o["targets"])
            allsecs += sum(e["seconds"] for e in o["targets"].values())
            decide += sel["seconds"]
            everything += 1 if sel["all_tests"] or (chosen and len(chosen) == len(o["targets"])) else 0
            fb += 1 if any(x.startswith("fallback") for x in sel["rules"]) else 0
        missed = sum(1 for r, k in muts if not (k & set(r["selections"][n]["tests"])))
        c = max(len(reals), 1)
        out.append(f"| {SHORT[n]} | {share / c:.2f} | {secs:.0f} of {allsecs:.0f} s | {decide:.0f} s ({decide / c:.1f} s per commit) | "
                   f"{int(everything)} | {int(fb)} | {missed} of {len(muts)} |")
    out.append("")
    return out


def everything_reasons(run: Run) -> list[str]:
    """H5: commits where the package graph runs every test target, by the kind of file that forced it."""
    reasons = Counter()
    total = 0
    for r, _ in run.reals():
        total += 1
        sel = r["selections"].get("package-graph")
        if not sel or not sel["all_tests"]:
            continue
        kinds = sorted({x.split(":", 1)[0] for x in sel["rules"]})
        reasons[" + ".join(kinds)] += 1
    if not total:
        return []
    n = sum(reasons.values())
    line = f"| {run.name} | {total} | {n} ({100 * n / total:.0f}%) | " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()) + " |"
    return [line]


def index_cost(run: Run) -> list[str]:
    """H4: index build versus query, against the plain build the oracle timed at the same commit."""
    if "compiler-index" not in run.names:
        return []
    build = query = plain = tests_all = tests_index = 0.0
    n = 0
    for r, o in run.reals():
        b, q = index_split(r["selections"]["compiler-index"])
        build, query = build + b, query + q
        plain += sum(x["seconds"] for x in o["build"].values())
        tests_all += sum(e["seconds"] for e in o["targets"].values())
        tests_index += sum(o["targets"][t]["seconds"] for t in r["selections"]["compiler-index"]["tests"] if t in o["targets"])
        n += 1
    if not n:
        return []
    saved = tests_all - tests_index
    return [f"| {run.name} | {n} | {build:.0f} s | {query:.0f} s | {plain:.0f} s | {saved:.0f} s | "
            f"{saved - build - query:+.0f} s | {saved - query:+.0f} s |"]


def civitas(run: Run, rebuild: list[dict]) -> list[str]:
    edits = json.loads((run.dir / "edits.json").read_text()) if (run.dir / "edits.json").exists() else None
    if not edits:
        return []
    by_head = edits["commits"]
    info = {e["id"]: e for e in edits["edits"]}
    rb = {r["head"]: r for r in rebuild}
    muts = defaultdict(list)
    for r, killers in run.mutants():
        muts[r["of"]].append((r, killers))
    names = [n for n in run.names if n != "run-all"]
    head = "| Edit | Kind | Module (depth) | " + " | ".join(SHORT[n] for n in names) + \
           " | Bazel modules compiled | Bazel tests rerun | SwiftPM modules compiled | Seeded bugs caught | Missed by |"
    out = [head, "|" + "---|" * (head.count("|") - 1)]
    groups = defaultdict(lambda: defaultdict(list))
    for r, o in run.reals():
        eid = by_head.get(r["head"])
        if eid is None:
            continue
        e = info[eid]
        counts = [len(r["selections"][n]["tests"]) for n in names]
        b = rb.get(r["head"], {})
        bz, sp = b.get("bazel", {}), b.get("swiftpm", {})
        caught = muts.get(r["head"], [])
        missed = sorted({SHORT[n] for m, k in caught for n in names if not (k & set(m["selections"][n]["tests"]))})
        out.append(f"| {eid} | {e['kind']} | {e['module']} ({e['depth']}) | " + " | ".join(str(c) for c in counts) +
                   f" | {len(bz.get('compiled', [])) if bz else ''} | {len(bz.get('tests_rerun', [])) if bz else ''} | "
                   f"{len(sp.get('compiled', [])) if sp else ''} | {len(caught)} | {', '.join(missed) or '-'} |")
        group = e["kind"].split("-")[0] if e["depth"] != "none" else "not a source file"
        for n, c in zip(names, counts):
            groups[group][n].append(c / max(len(o["targets"]), 1))
    out += ["", "Mean share of the 17 test targets by edit kind:", "",
            "| Edit kind | " + " | ".join(SHORT[n] for n in names) + " |", "|---|" + "---|" * len(names)]
    for g, d in sorted(groups.items()):
        out.append(f"| {g} | " + " | ".join(f"{sum(d[n]) / len(d[n]):.2f}" for n in names) + " |")
    return out


def traps(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    names = list(rows[0]["selectors"])
    out = ["| Trap | Construct | Valid | " + " | ".join(SHORT[n] for n in names) + " |",
           "|---|---|---|" + "---|" * len(names)]
    for r in rows:
        cells = []
        for n in names:
            s = r["selectors"][n]
            cells.append(("caught" if s["safe"] else "**missed**") + ("" if s["precise"] else ", wide"))
        out.append(f"| {r['id']} | {r['construct'].split(':')[0]} | {'yes' if r['valid'] else 'NO'} | " + " | ".join(cells) + " |")
    return out


def main() -> None:
    root = Path(sys.argv[1])
    runs = [Run(d) for d in sorted(root.iterdir()) if (d / "selections.jsonl").exists()]
    rebuild = load(root / "civitas-rebuild" / "rebuild.jsonl")
    trap_rows = load(root / "traps" / "traps.jsonl")
    out = [f"# Results: {root.name}", "",
           "Generated by `scripts/report.py`. Shares are of test targets. Deciding time is wall time to choose, "
           "including the compiler index's indexed build and Bazel's queries. A seeded bug is missed when a selector "
           "skips every test that catches it.", "", "## Per subject", ""]
    for run in runs:
        out += summary(run)
    rows = [l for run in runs for l in everything_reasons(run)]
    if rows:
        out += ["## Commits where the package graph runs everything (H5)", "",
                "| Subject | Commits | Graph runs everything | Why |", "|---|---|---|---|", *rows, ""]
    rows = [l for run in runs for l in index_cost(run)]
    if rows:
        out += ["## What the compiler index costs (H4)", "",
                "Index build is the incremental indexed build of each base. Query is the rest of its deciding time. "
                "Plain build is the oracle's incremental build of the same commit without indexing. Saved is test time "
                "not run. Net stand-alone counts the indexed build; net with a CI build assumes CI already builds with "
                "indexing on, so only the query is added.", "",
                "| Subject | Commits | Index build | Query | Plain build | Test time saved | Net, stand-alone | Net, with a CI build |",
                "|---|---|---|---|---|---|---|---|", *rows, ""]
    civ = next((r for r in runs if r.name == "civitas"), None)
    if civ:
        rows = civitas(civ, rebuild)
        if rows:
            out += ["## Civitas edit catalogue (H1, H2, H2b, H3, H7, H8)", "",
                    "Test targets selected per edit (17 in all). Bazel and SwiftPM columns come from the rebuild study: "
                    "modules that recompiled, and Bazel test targets that ran rather than came from cache.", "", *rows, ""]
    rows = traps(trap_rows)
    if rows:
        out += ["## Traps (H9)", "", *rows, ""]
    classes = sorted(d for d in root.iterdir() if d.name.endswith("-classes") and (d / "units-selections.jsonl").exists())
    if classes:
        res = subprocess.run([sys.executable, str(Path(__file__).with_name("units-analyze.py")), *map(str, classes)],
                             capture_output=True, text=True, check=True)
        out += ["", res.stdout.replace("## Test-class pass", "## Test-class pass (H6)", 1)]
    print("\n".join(out))


if __name__ == "__main__":
    main()
