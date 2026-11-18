"""Ground truth: run every test target at a revision and record which ones fail.

Run once per commit; every selector is then scored offline against the same record, so a
selector's misses and its time saved come from one set of test runs.

Needs the subject's Swift toolchain (Linux container or macOS). A target counts as running zero
tests only when neither XCTest nor swift-testing reports running any.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import time
from pathlib import Path

from .graph import load_graph
from .pins import apply_pins, pins
from .units import TOP_LEVEL


def _run(cmd: list[str], cwd: str, timeout: int) -> tuple[int, float, str]:
    """Run in its own process group, so a timeout also stops the test helpers swift test starts."""
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, time.perf_counter() - t0, out + err
    except subprocess.TimeoutExpired:
        # swift test's helper starts its own process group, so kill the whole tree, children first
        for pid in reversed(_tree(p.pid)):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        p.communicate()
        return TIMEOUT, time.perf_counter() - t0, "timeout"


def _tree(root: int) -> list[int]:
    """`root` and every process below it, parents before children."""
    out = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True).stdout.split()
    children: dict[int, list[int]] = {}
    for pid, ppid in zip(out[::2], out[1::2]):
        children.setdefault(int(ppid), []).append(int(pid))
    order, stack = [], [root]
    while stack:
        pid = stack.pop()
        order.append(pid)
        stack.extend(children.get(pid, []))
    return order


TIMEOUT = 124
# A test target that runs longer than this is stopped and counted as failing. A seeded bug can make a
# test wait forever (a server that never answers), and that is a catch, not a reason to wait an hour.
TEST_TIMEOUT = int(os.environ.get("TSEL_TEST_TIMEOUT", "600"))


def _tail(log: str) -> str:
    return log[-8000:]


XCTEST_CASE = re.compile(r"Test Case '-\[(\w+)\.(\w+) (\w+)\]' (passed|failed|skipped) \((\d+\.\d+) seconds\)")


def unit_results(target: str, log: str, xml_path: Path) -> dict[str, dict]:
    """Per test class: tests run, tests failed, seconds. XCTest from console lines, swift-testing from XML."""
    units: dict[str, dict] = {}

    def add(unit: str, failed: bool, secs: float) -> None:
        u = units.setdefault(unit, {"tests": 0, "failed": 0, "seconds": 0.0})
        u["tests"] += 1
        u["failed"] += 1 if failed else 0
        u["seconds"] = round(u["seconds"] + secs, 4)

    for m in XCTEST_CASE.finditer(log):
        if m.group(1) == target:
            add(m.group(2), m.group(4) == "failed", float(m.group(5)))
    st = xml_path.with_name(xml_path.stem + "-swift-testing.xml")
    if st.exists():
        try:
            root = ET.parse(st).getroot()
        except ET.ParseError:
            root = None
        for case in (root.iter("testcase") if root is not None else []):
            cls = case.get("classname", "")
            rest = cls[len(target) + 1:] if cls.startswith(target + ".") else ""
            unit = re.split(r"[./]", rest)[0] if rest else TOP_LEVEL
            add(unit, case.find("failure") is not None or case.find("error") is not None,
                float(case.get("time", "0") or 0))
    return units


def run_oracle(repo: str, rev: str, out_path: str, package_dirs: list[str] | None = None,
               reruns: int = 2, timeout: int = 3600, worktree: str | None = None, units: bool = False) -> dict:
    """Check out `rev` in a scratch worktree, build tests once, then run each test target alone.

    With `worktree`, that worktree is kept and reused, so consecutive revisions build incrementally.
    """
    package_dirs = package_dirs or ["."]
    keep = worktree is not None
    wt = Path(worktree) if keep else Path(repo).resolve().parent / f".tsel-worktree-{rev[:12]}"
    if keep and wt.exists():
        subprocess.run(["git", "-C", str(wt), "checkout", "--force", "--detach", rev], check=True, capture_output=True)
        # files a test run wrote (snapshots, records) must not leak into the next revision; keep .build
        subprocess.run(["git", "-C", str(wt), "clean", "-fdq"], check=True, capture_output=True)
    else:
        subprocess.run(["git", "-C", repo, "worktree", "add", "--force", "--detach", str(wt), rev],
                       check=True, capture_output=True)
    try:
        graph = load_graph(str(wt), package_dirs)
        record: dict = {"rev": rev, "build": {}, "targets": {}}
        if pins():
            record["pins"] = [f"{n}={v}" for n, v in pins()]
        for d in package_dirs:
            apply_pins(str(wt / d))
            code, secs, log = _run(["swift", "build", "--build-tests"], str(wt / d), timeout)
            record["build"][d] = {"code": code, "seconds": round(secs, 2), "log_tail": _tail(log) if code else ""}
        for tid in sorted(graph.test_targets()):
            t = graph.targets[tid]
            cmd = ["swift", "test", "--skip-build", "--filter", f"^{t.name}\\."]
            xml_dir = tempfile.mkdtemp(prefix="tsel-xunit-") if units else None
            first = cmd + (["--xunit-output", str(Path(xml_dir) / "results.xml")] if units else [])
            code, secs, log = _run(first, str(wt / t.package_dir), min(timeout, TEST_TIMEOUT))
            unit_rows = unit_results(t.name, log, Path(xml_dir) / "results.xml") if units else None
            if xml_dir:
                shutil.rmtree(xml_dir, ignore_errors=True)
            entry = {"code": code, "seconds": round(secs, 2), "flaky": False}
            if unit_rows is not None:
                entry["units"] = unit_rows
            if code == TIMEOUT:
                entry["timeout"] = True   # a hang is not rerun: it would only hang again
                entry["log_tail"] = _tail(log)
            elif code != 0:
                # re-run before calling it a failure: flaky tests look like misses
                again = [_run(cmd, str(wt / t.package_dir), min(timeout, TEST_TIMEOUT))[0] for _ in range(reruns)]
                entry["flaky"] = any(c == 0 for c in again)
                entry["log_tail"] = _tail(log)
            # XCTest prints "Executed 0 tests" for empty wrapper suites even when tests ran, so count cases
            xctest_ran = len(XCTEST_CASE.findall(log))
            swift_testing_ran = max((int(n) for n in re.findall(r"Test run with (\d+) tests?", log)), default=0)
            if code == 0 and xctest_ran == 0 and swift_testing_ran == 0:
                entry["zero_tests"] = True   # a run of zero tests counts as a failure of the harness
            record["targets"][tid] = entry
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a") as fh:
            fh.write(json.dumps(record) + "\n")
        return record
    finally:
        if not keep:
            subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", str(wt)], capture_output=True)
