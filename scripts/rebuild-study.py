#!/usr/bin/env python3
"""Rebuild versus rerun (H3): replay a subject's history with incremental Bazel and SwiftPM builds.

    scripts/rebuild-study.py ../subjects/civitas <end commit> <count> results/macos/civitas-rebuild

For each commit, in order, in one kept worktree (so every step is incremental from the one before):

- Bazel: `bazel test //...` with the build event log. Records which modules ran a SwiftCompile action,
  which test targets ran rather than came from cache, and the wall time.
- SwiftPM: `swift build --build-tests`. Records which modules compiled and the wall time.

The commit before the first is built once to warm both, and not recorded. Resumes if rerun.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsel.replay import commits

repo, end, count, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
bazel = os.environ.get("TSEL_BAZEL") or shutil.which("bazelisk") or "bazel"
wt = Path(os.environ.get("TSEL_CACHE", Path.home() / ".cache" / "tsel")) / "rebuild" / Path(repo).resolve().name
rows_path = out / "rebuild.jsonl"
done = {json.loads(l)["head"] for l in open(rows_path)} if rows_path.exists() else set()


def sh(*args: str, cwd: Path | str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True)


def checkout(rev: str) -> None:
    if not wt.exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", repo, "worktree", "add", "--force", "--detach", str(wt), rev], check=True,
                       capture_output=True)
    else:
        subprocess.run(["git", "-C", str(wt), "checkout", "--force", "--detach", rev], check=True, capture_output=True)


def bazel_step() -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        bep = f.name
    t0 = time.perf_counter()
    r = sh(bazel, "test", "//...", f"--build_event_json_file={bep}", "--build_event_publish_all_actions", cwd=wt)
    secs = time.perf_counter() - t0
    compiled, rerun, cached, actions = set(), set(), set(), {}
    for line in open(bep):
        e = json.loads(line)
        a = e.get("action")
        if a is not None:
            actions[a.get("type")] = actions.get(a.get("type"), 0) + 1
            if a.get("type") == "SwiftCompile":
                compiled.add(e["id"]["actionCompleted"].get("label", "").rsplit(":", 1)[-1])
        tr = e.get("testResult")
        if tr is not None:
            name = e["id"]["testResult"]["label"].rsplit(":", 1)[-1]
            (cached if tr.get("cachedLocally") else rerun).add(name)
    os.unlink(bep)
    return {"code": r.returncode, "seconds": round(secs, 2), "compiled": sorted(compiled),
            "tests_rerun": sorted(rerun), "tests_cached": sorted(cached), "actions": actions}


def swiftpm_step() -> dict:
    t0 = time.perf_counter()
    r = sh("swift", "build", "--build-tests", "-v", cwd=wt)
    secs = time.perf_counter() - t0
    log = r.stdout + r.stderr
    modules = set()
    for line in log.splitlines():
        m = re.search(r"-module-name (\w+)", line)
        if m and m.group(1) != "main" and ("builtin-Swift" in line or "swiftc" in line or "swift-frontend" in line):
            modules.add(m.group(1))
    return {"code": r.returncode, "seconds": round(secs, 2), "compiled": sorted(modules)}


revs = commits(repo, end, count + 1)
checkout(revs[0])
if not done:
    bazel_step()
    swiftpm_step()
with open(rows_path, "a") as fh:
    for head in revs[1:]:
        if head in done:
            continue
        checkout(head)
        subject = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%s", head], capture_output=True,
                                 text=True).stdout.strip()
        row = {"head": head, "subject": subject, "bazel": bazel_step(), "swiftpm": swiftpm_step()}
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        b, s = row["bazel"], row["swiftpm"]
        print(f"{subject[:40]:40s} bazel {b['seconds']:6.1f}s compiled={len(b['compiled'])} rerun={len(b['tests_rerun'])}"
              f" | swiftpm {s['seconds']:6.1f}s compiled={len(s['compiled'])}", flush=True)
