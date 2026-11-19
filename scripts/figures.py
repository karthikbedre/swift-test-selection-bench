#!/usr/bin/env python3
"""Figures for the paper, each with the CSV of exactly the values it plots.

    scripts/figures.py results/macos figures/

Needs matplotlib (pip install -e '.[figures]'). Writes 300 dpi PNGs:

1. fig1-target-share       mean share of test targets selected, per subject and selector
2. fig2-runs-everything    share of real commits where the package graph runs every test (the CSV splits it by reason)
3. fig3-index-cost         compiler index: test time saved against its indexed builds and queries
4. fig4-civitas-edits      test targets selected for each Civitas edit, per selector
5. fig5-rebuild-rerun      Swift modules Bazel recompiled and tests it reran, for each Civitas edit
6. fig6-class-time         class test time selected relative to the package graph (test-class pass)

Colours follow the selector in every figure: package graph, Tree-sitter, compiler index, Bazel hash and
interface-only take the first five slots of a fixed categorical palette, in that order.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
SUBJECTS = [("swift-argument-parser", "swift-argument-parser"), ("swift-nio", "swift-nio"),
            ("hummingbird", "Hummingbird"), ("civitas", "Civitas")]
PUBLIC = SUBJECTS[:3]
COLOR = {"package-graph": "#2a78d6", "tree-sitter": "#eb6834", "compiler-index": "#1baf7a",
         "hash-cache": "#eda100", "interface-only": "#e87ba4"}
NAME = {"package-graph": "Package graph", "tree-sitter": "Tree-sitter", "compiler-index": "Compiler index",
        "hash-cache": "Bazel hash", "interface-only": "Interface-only"}
INK, MUTED, GRID, NEUTRAL = "#0b0b0b", "#52514e", "#e4e3df", "#8a8984"

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "figure.dpi": 100, "savefig.dpi": 300, "savefig.bbox": "tight", "legend.frameon": False,
})


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.argv, saved = [str(HERE)], sys.argv          # the scripts read argv only under __main__
    spec.loader.exec_module(mod)
    sys.argv = saved
    return mod


report = load_module("report")


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def bar_labels(ax, bars, fmt: str, horizontal: bool = True) -> None:
    for b in bars:
        v = b.get_width() if horizontal else b.get_height()
        if horizontal:
            ax.text(b.get_x() + v + 0.01 * ax.get_xlim()[1], b.get_y() + b.get_height() / 2, fmt.format(v),
                    va="center", ha="left", fontsize=7.5, color=MUTED)
        else:
            ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v), va="bottom", ha="center", fontsize=7.5,
                    color=MUTED)


def kind_label(kind: str) -> str:
    return kind.replace("ci-workflow", "CI workflow").replace("-", " ")


def fig1(root: Path, out: Path) -> None:
    sels = ["package-graph", "tree-sitter", "compiler-index"]
    rows = []
    for key, label in SUBJECTS:
        run = report.Run(root / key)
        reals = list(run.reals())
        for s in sels:
            share = sum(len(r["selections"][s]["tests"]) / max(len(o["targets"]), 1) for r, o in reals) / len(reals)
            rows.append([label, NAME[s], share, len(reals)])
    write_csv(out / "fig1-target-share.csv", ["subject", "selector", "mean_share_of_test_targets", "commits"],
              [[a, b, round(c, 4), d] for a, b, c, d in rows])
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    h = 0.24
    for i, s in enumerate(sels):
        ys = [k + (i - 1) * (h + 0.02) for k in range(len(SUBJECTS))]
        vals = [r[2] for r in rows if r[1] == NAME[s]]
        bars = ax.barh(ys, vals, height=h, color=COLOR[s], label=NAME[s])
        bar_labels(ax, bars, "{:.2f}")
    ax.set_yticks(range(len(SUBJECTS)), [label for _, label in SUBJECTS])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.08)
    ax.set_xlabel("Mean share of test targets selected per commit")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8)
    fig.savefig(out / "fig1-target-share.png")
    plt.close(fig)


def fig2(root: Path, out: Path) -> None:
    order = [("build_setting", "Build setting or CI file"), ("manifest", "Package manifest"),
             ("unowned", "File no target owns")]
    rows = []
    for key, label in SUBJECTS:
        run = report.Run(root / key)
        reals = list(run.reals())
        c = Counter()
        for r, _ in reals:
            g = r["selections"]["package-graph"]
            if g["all_tests"]:
                kinds = {x.split(":", 1)[0] for x in g["rules"]}
                c["manifest" if "manifest" in kinds else "build_setting" if "build_setting" in kinds else "unowned"] += 1
        for k, name in order:
            rows.append([label, name, c[k], len(reals), round(c[k] / len(reals), 3)])
    write_csv(out / "fig2-runs-everything.csv", ["subject", "reason", "commits", "total_commits", "share"], rows)
    fig, ax = plt.subplots(figsize=(6.2, 2.4))
    totals = []
    for k, (key, label) in enumerate(SUBJECTS):
        share = sum(r[4] for r in rows if r[0] == label)
        totals.append(share)
        b = ax.barh([k], [share], height=0.5, color=COLOR["package-graph"])
        bar_labels(ax, b, "{:.0%}")
    ax.set_yticks(range(len(SUBJECTS)), [label for _, label in SUBJECTS])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Real commits where the package graph runs every test")
    ax.grid(axis="y", visible=False)
    fig.savefig(out / "fig2-runs-everything.png")
    plt.close(fig)


def fig3(root: Path, out: Path) -> None:
    rows = []
    for key, label in SUBJECTS:
        run = report.Run(root / key)
        build = query = saved = 0.0
        n = 0
        for r, o in run.reals():
            b, q = report.index_split(r["selections"]["compiler-index"])
            build, query = build + b, query + q
            chosen = r["selections"]["compiler-index"]["tests"]
            saved += sum(e["seconds"] for e in o["targets"].values()) - sum(
                o["targets"][t]["seconds"] for t in chosen if t in o["targets"])
            n += 1
        rows.append([label, n, round(saved / n, 2), round(build / n, 2), round(query / n, 2),
                     round((saved - build - query) / n, 2)])
    write_csv(out / "fig3-index-cost.csv", ["subject", "commits", "test_time_saved_s_per_commit",
                                             "index_build_s_per_commit", "query_s_per_commit", "net_s_per_commit"], rows)
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    h = 0.34
    for k, r in enumerate(rows):
        b1 = ax.barh([k - h / 2 - 0.01], [r[2]], height=h, color=NEUTRAL, label="Test time saved" if k == 0 else None)
        b2 = ax.barh([k + h / 2 + 0.01], [r[3] + r[4]], height=h, color=COLOR["compiler-index"],
                     label="Deciding time (indexed build and query)" if k == 0 else None)
        bar_labels(ax, b1, "{:.1f} s")
        bar_labels(ax, b2, "{:.1f} s")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(max(r[2], r[3] + r[4]) for r in rows) * 1.18)
    ax.set_xlabel("Seconds per commit")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=8)
    fig.savefig(out / "fig3-index-cost.png")
    plt.close(fig)


def fig4(root: Path, out: Path) -> None:
    run = report.Run(root / "civitas")
    edits = json.loads((root / "civitas" / "edits.json").read_text())
    info = {e["id"]: e for e in edits["edits"]}
    sels = ["package-graph", "tree-sitter", "compiler-index", "interface-only", "hash-cache"]
    rows = []
    for r, o in run.reals():
        eid = edits["commits"].get(r["head"])
        if eid:
            e = info[eid]
            rows.append([eid, e["kind"], e["module"], e["depth"]] + [len(r["selections"][s]["tests"]) for s in sels])
    write_csv(out / "fig4-civitas-edits.csv", ["edit", "kind", "module", "depth"] + sels, rows)
    data = [r[4:] for r in rows]
    fig, ax = plt.subplots(figsize=(5.6, 7.2))
    im = ax.imshow(data, cmap="Blues", vmin=0, vmax=17, aspect="auto")
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(j, i, str(v), ha="center", va="center", fontsize=7.5, color="white" if v > 10 else INK)
    ax.set_xticks(range(len(sels)), [NAME[s] for s in sels], rotation=30, ha="right")
    ax.set_yticks(range(len(rows)), [f"{r[0]}  {kind_label(r[1])}, {r[2] if r[2] != '-' else 'repository'}"
                                      for r in rows], fontsize=7.5)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("Test targets selected (of 17)")
    cb.outline.set_visible(False)
    fig.savefig(out / "fig4-civitas-edits.png")
    plt.close(fig)


def fig5(root: Path, out: Path) -> None:
    edits = json.loads((root / "civitas" / "edits.json").read_text())
    info = {e["id"]: e for e in edits["edits"]}
    rows = []
    for l in open(root / "civitas-rebuild" / "rebuild.jsonl"):
        r = json.loads(l)
        eid = edits["commits"].get(r["head"])
        if eid:
            b, s = r["bazel"], r["swiftpm"]
            rows.append([eid, info[eid]["kind"], info[eid]["module"], len(b["compiled"]), len(b["tests_rerun"]),
                         len(s["compiled"]), b["seconds"], s["seconds"]])
    write_csv(out / "fig5-rebuild-rerun.csv", ["edit", "kind", "module", "bazel_modules_compiled",
                                                "bazel_tests_rerun", "swiftpm_modules_compiled", "bazel_s", "swiftpm_s"], rows)
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 6.8), sharey=True)
    ys = range(len(rows))
    for ax, col, title, xmax in ((axes[0], 3, "Swift modules recompiled (Bazel)", 36), (axes[1], 4, "Test targets rerun (Bazel)", 17)):
        bars = ax.barh(list(ys), [r[col] for r in rows], height=0.6, color=COLOR["hash-cache"])
        ax.set_xlim(0, xmax * 1.15)
        bar_labels(ax, bars, "{:.0f}")
        ax.set_title(title, fontsize=9, loc="left")
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(list(ys), [f"{r[0]}  {kind_label(r[1])}" for r in rows], fontsize=7.5)
    axes[0].invert_yaxis()
    fig.savefig(out / "fig5-rebuild-rerun.png")
    plt.close(fig)


def fig6(root: Path, out: Path) -> None:
    sels = ["tree-sitter", "compiler-index"]
    rows = []
    for key, label in PUBLIC:
        d = root / f"{key}-classes"
        sel_rows = {json.loads(l)["head"]: json.loads(l) for l in open(d / "units-selections.jsonl")}
        orc = {json.loads(l)["rev"]: json.loads(l) for l in open(d / "units-oracle.jsonl")}
        secs = Counter()
        n = 0
        for head, r in sel_rows.items():
            o = orc.get(head)
            if r["kind"] != "real" or not o or any(b["code"] != 0 for b in o["build"].values()):
                continue
            known = {(t, u) for t, us in r["units_total"].items() for u in us}
            unit_secs = {(t, u): v["seconds"] for t, e in o["targets"].items() for u, v in e.get("units", {}).items()
                         if (t, u) in known}
            n += 1
            for s in ["package-graph"] + sels:
                chosen = {(t, u) for t, us in r["selections"][s]["units"].items() for u in us}
                secs[s] += sum(v for k, v in unit_secs.items() if k in chosen)
        for s in sels:
            rows.append([label, NAME[s], n, round(secs[s], 1), round(secs["package-graph"], 1),
                         round(secs[s] / secs["package-graph"], 3)])
    write_csv(out / "fig6-class-time.csv", ["subject", "selector", "commits", "class_test_s", "graph_class_test_s",
                                             "relative_to_graph"], rows)
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    h = 0.34
    for i, s in enumerate(sels):
        vals = [r[5] for r in rows if r[1] == NAME[s]]
        ys = [k + (i - 0.5) * (h + 0.02) for k in range(len(PUBLIC))]
        bars = ax.barh(ys, vals, height=h, color=COLOR[s], label=NAME[s])
        bar_labels(ax, bars, "{:.0%}")
    ax.axvline(1.0, color=COLOR["package-graph"], linewidth=1.2, label="Package graph (100%)")
    ax.set_yticks(range(len(PUBLIC)), [label for _, label in PUBLIC])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.15)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Class test time selected, relative to the package graph")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=8)
    fig.savefig(out / "fig6-class-time.png")
    plt.close(fig)


def main() -> None:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for f in (fig1, fig2, fig3, fig4, fig5, fig6):
        f(root, out)
        print("wrote", f.__name__)


if __name__ == "__main__":
    main()
