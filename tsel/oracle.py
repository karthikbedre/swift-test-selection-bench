"""Ground truth: run every test target at a revision and record which ones fail.

Run once per commit; every selector is then scored offline against the same record, so a
selector's misses and its time saved come from one set of test runs.

Needs the subject's Swift toolchain (Linux container or macOS). Not exercised in this repo's
own unit tests, which run without a toolchain.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from .graph import load_graph


def _run(cmd: list[str], cwd: str, timeout: int) -> tuple[int, float, str]:
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, time.perf_counter() - t0, p.stdout[-4000:] + p.stderr[-4000:]
    except subprocess.TimeoutExpired:
        return 124, time.perf_counter() - t0, "timeout"


def run_oracle(repo: str, rev: str, out_path: str, package_dirs: list[str] | None = None,
               reruns: int = 2, timeout: int = 3600) -> dict:
    """Check out `rev` in a scratch worktree, build tests once, then run each test target alone."""
    package_dirs = package_dirs or ["."]
    wt = Path(repo).resolve().parent / f".tsel-worktree-{rev[:12]}"
    subprocess.run(["git", "-C", repo, "worktree", "add", "--force", "--detach", str(wt), rev],
                   check=True, capture_output=True)
    try:
        graph = load_graph(str(wt), package_dirs)
        record: dict = {"rev": rev, "build": {}, "targets": {}}
        for d in package_dirs:
            code, secs, log = _run(["swift", "build", "--build-tests"], str(wt / d), timeout)
            record["build"][d] = {"code": code, "seconds": round(secs, 2), "log_tail": log if code else ""}
        for tid in sorted(graph.test_targets()):
            t = graph.targets[tid]
            cmd = ["swift", "test", "--skip-build", "--filter", f"^{t.name}\\."]
            code, secs, log = _run(cmd, str(wt / t.package_dir), timeout)
            entry = {"code": code, "seconds": round(secs, 2), "flaky": False}
            if code != 0:
                # re-run before calling it a failure: flaky tests look like misses
                again = [_run(cmd, str(wt / t.package_dir), timeout)[0] for _ in range(reruns)]
                entry["flaky"] = any(c == 0 for c in again)
                entry["log_tail"] = log
            if "Executed 0 tests" in log or "0 tests in 0 suites" in log:
                entry["zero_tests"] = True   # a run of zero tests counts as a failure of the harness
            record["targets"][tid] = entry
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a") as fh:
            fh.write(json.dumps(record) + "\n")
        return record
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", str(wt)], capture_output=True)
