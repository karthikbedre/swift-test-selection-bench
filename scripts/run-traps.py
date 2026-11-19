#!/usr/bin/env python3
"""Check every trap and score every selector on it.

    scripts/run-traps.py results/macos/traps [T002 T003 ...]

For each trap: commit it to a scratch repository, run the oracle at base (every test must pass), commit
the edit from trap.json, run the oracle at head (each `must_select` test must fail, each `may_skip` test
must pass), then run every selector on base..head. A selector is unsafe on a trap when it skips a
`must_select` target, and precise when it also skips the `may_skip` ones.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tsel.changes import read_changes
from tsel.graph import load_graph
from tsel.oracle import run_oracle
from tsel.selectors import SELECTORS

NAMES = ["package-graph", "tree-sitter", "compiler-index", "interface-only"]
GIT = ["-c", "user.name=trap", "-c", "user.email=trap@example.invalid"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *GIT, *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def failing(record: dict) -> set[str]:
    return {t.split("::")[1] for t, e in record["targets"].items() if e["code"] != 0 and not e.get("flaky")}


def run_trap(trap_dir: Path, scratch: Path) -> dict:
    trap = json.loads((trap_dir / "trap.json").read_text())
    repo = scratch / trap_dir.name
    shutil.copytree(trap_dir, repo, ignore=shutil.ignore_patterns(".build", ".swiftpm"))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    e = trap["edit"]
    f = repo / e["file"]
    text = f.read_text()
    assert text.count(e["find"]) == 1, f"{trap['id']}: edit text not found exactly once"
    f.write_text(text.replace(e["find"], e["replace"]))
    git(repo, "commit", "-q", "-am", "edit")
    head = git(repo, "rev-parse", "HEAD")

    log = str(scratch / f"{trap['id']}-oracle.jsonl")
    at_base = run_oracle(str(repo), base, log, reruns=0)
    at_head = run_oracle(str(repo), head, log, reruns=1)
    fail_base, fail_head = failing(at_base), failing(at_head)
    valid = (not fail_base and set(trap["must_select"]) <= fail_head
             and not (set(trap.get("may_skip", [])) & fail_head))

    graph = load_graph(str(repo), ["."])
    changes = read_changes(str(repo), base, head)
    selectors = {}
    for name in NAMES:
        sel = SELECTORS[name]().select(changes, graph)
        chosen = {t.split("::")[1] for t in sel.tests}
        selectors[name] = {
            "tests": sorted(chosen),
            "safe": set(trap["must_select"]) <= chosen,
            "precise": not (set(trap.get("may_skip", [])) & chosen),
            "rules": sel.rules,
        }
    return {"id": trap["id"], "construct": trap["construct"], "valid": valid,
            "failing_at_base": sorted(fail_base), "failing_at_head": sorted(fail_head),
            "must_select": trap["must_select"], "may_skip": trap.get("may_skip", []), "selectors": selectors}


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    wanted = set(sys.argv[2:])
    traps = sorted(p.parent for p in (ROOT / "traps").glob("T*/trap.json"))
    rows = []
    with tempfile.TemporaryDirectory(prefix="tsel-traps-") as tmp:
        for t in traps:
            if wanted and t.name.split("-")[0] not in wanted:
                continue
            row = run_trap(t, Path(tmp))
            rows.append(row)
            marks = " ".join(f"{n}={'safe' if s['safe'] else 'MISS'}{'' if s['precise'] else '(wide)'}"
                             for n, s in row["selectors"].items())
            print(f"{row['id']} valid={row['valid']} {marks}", flush=True)
    (out / "traps.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    main()
