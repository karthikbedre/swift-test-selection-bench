"""Dependency pins for subjects that do not commit a Package.resolved.

Without a lock file every build resolves the newest allowed dependency versions, which can break old
commits: swift-system 1.7.0 made `FileType` public, which clashes with swift-nio's own `FileType` in its
tests. A subject's `dependency_pins` in subjects.json reaches the harness as TSEL_PINS
("name=version,name=version") and is applied with `swift package resolve <name> --version <version>`
before every build. Package.resolved is ignored by such subjects, so the pin survives checkouts.
"""
from __future__ import annotations

import os
import subprocess
import time


def pins() -> list[tuple[str, str]]:
    spec = os.environ.get("TSEL_PINS", "").strip()
    return [tuple(p.split("=", 1)) for p in spec.split(",") if "=" in p]  # type: ignore[misc]


def apply_pins(package_dir: str) -> float:
    """Pin each dependency in `package_dir`. Returns the seconds spent, so callers can leave them out of timings."""
    t0 = time.perf_counter()
    for name, version in pins():
        subprocess.run(["swift", "package", "resolve", name, "--version", version], cwd=package_dir,
                       capture_output=True, text=True)
    return time.perf_counter() - t0
