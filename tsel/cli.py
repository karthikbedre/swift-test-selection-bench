"""Command line: `python -m tsel <command> ...`."""
from __future__ import annotations

import argparse
import json
import sys

from .changes import read_changes
from .graph import load_graph
from .selectors import SELECTORS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tsel", description="Change-based test selection for Swift: selectors and harness")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("graph", help="print the package graph of a checked-out package")
    g.add_argument("repo")
    g.add_argument("--package-dir", action="append", dest="package_dirs")
    g.add_argument("--no-toolchain", action="store_true", help="use the Tree-sitter manifest reader")

    s = sub.add_parser("select", help="select test targets for one change")
    s.add_argument("repo")
    s.add_argument("base")
    s.add_argument("head")
    s.add_argument("--selector", action="append", choices=sorted(SELECTORS), dest="selectors")
    s.add_argument("--package-dir", action="append", dest="package_dirs")
    s.add_argument("--no-toolchain", action="store_true")

    r = sub.add_parser("replay", help="record selections for the last N first-parent commits")
    r.add_argument("repo")
    r.add_argument("--end", default="HEAD")
    r.add_argument("--count", type=int, default=300)
    r.add_argument("--selector", action="append", choices=sorted(SELECTORS), dest="selectors")
    r.add_argument("--package-dir", action="append", dest="package_dirs")
    r.add_argument("--out", required=True)

    o = sub.add_parser("oracle", help="run every test target at one revision (needs a Swift toolchain)")
    o.add_argument("repo")
    o.add_argument("rev")
    o.add_argument("--package-dir", action="append", dest="package_dirs")
    o.add_argument("--out", required=True)

    sc = sub.add_parser("score", help="join selections with oracle runs")
    sc.add_argument("selections")
    sc.add_argument("oracle")
    sc.add_argument("--csv", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "graph":
        graph = load_graph(a.repo, a.package_dirs, prefer_toolchain=not a.no_toolchain)
        json.dump({"approximate": graph.approximate, "targets": graph.describe()}, sys.stdout, indent=2)
        print()
    elif a.cmd == "select":
        graph = load_graph(a.repo, a.package_dirs, prefer_toolchain=not a.no_toolchain)
        changes = read_changes(a.repo, a.base, a.head)
        names = a.selectors or ["run-all", "package-graph", "tree-sitter"]
        out = {n: SELECTORS[n]().select(changes, graph).to_json() for n in names}
        json.dump(out, sys.stdout, indent=2)
        print()
    elif a.cmd == "replay":
        from .replay import replay
        names = a.selectors or ["run-all", "package-graph", "tree-sitter"]
        n = replay(a.repo, a.end, a.count, names, a.out, a.package_dirs)
        print(f"replayed {n} commits -> {a.out}")
    elif a.cmd == "oracle":
        from .oracle import run_oracle
        rec = run_oracle(a.repo, a.rev, a.out, a.package_dirs)
        failing = [t for t, e in rec["targets"].items() if e["code"] != 0]
        print(f"{len(rec['targets'])} test targets, {len(failing)} failing -> {a.out}")
    elif a.cmd == "score":
        from .score import score
        json.dump(score(a.selections, a.oracle, a.csv), sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
