"""Join selections with oracle runs into per-commit, per-selector rows and a summary."""
from __future__ import annotations

import csv
import json
from collections import defaultdict


def _load(path: str) -> list[dict]:
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def score(selections_path: str, oracle_path: str, out_csv: str) -> dict:
    oracle = {r["rev"]: r for r in _load(oracle_path)}
    rows = []
    for rec in _load(selections_path):
        o = oracle.get(rec["head"])
        if o is None:
            continue
        failing = {t for t, e in o["targets"].items() if e["code"] != 0 and not e.get("flaky")}
        all_secs = sum(e["seconds"] for e in o["targets"].values())
        for name, sel in rec["selections"].items():
            if "error" in sel:
                continue
            chosen = set(sel["tests"])
            missed = failing - chosen
            rows.append({
                "head": rec["head"], "selector": name,
                "selected": len(chosen), "available": len(o["targets"]),
                "failing": len(failing), "missed": len(missed), "missed_targets": ";".join(sorted(missed)),
                "test_seconds": round(sum(o["targets"][t]["seconds"] for t in chosen if t in o["targets"]), 2),
                "all_test_seconds": round(all_secs, 2), "selection_seconds": sel["seconds"],
                "fallbacks": sum(1 for r in sel["rules"] if r.startswith(("fallback:", "manifest", "build_setting", "unowned"))),
            })
    with open(out_csv, "w", newline="") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    summary: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        s = summary[r["selector"]]
        s["commits"] += 1
        s["unsafe_commits"] += 1 if r["missed"] else 0
        s["selected_share"] += r["selected"] / max(r["available"], 1)
        s["test_seconds"] += r["test_seconds"] + r["selection_seconds"]
        s["all_test_seconds"] += r["all_test_seconds"]
    out = {}
    for name, s in summary.items():
        n = s["commits"] or 1
        out[name] = {"commits": int(s["commits"]), "unsafe_commits": int(s["unsafe_commits"]),
                     "mean_selected_share": round(s["selected_share"] / n, 3),
                     "time_saved_share": round(1 - s["test_seconds"] / max(s["all_test_seconds"], 1e-9), 3)}
    return out
