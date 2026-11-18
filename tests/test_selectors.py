"""Selector behaviour on the sample package and trap T001. Needs git and the Python deps only."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tsel.changes import FileClass, classify

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path,cls", [
    ("Package.swift", FileClass.MANIFEST), ("Package.resolved", FileClass.MANIFEST),
    ("Sources/A/x.swift", FileClass.SWIFT_SOURCE), ("Tests/ATests/x.swift", FileClass.SWIFT_TEST),
    ("Tests/ATests/Fixtures/a.json", FileClass.RESOURCE), ("Sources/A/Queries/q.graphql", FileClass.GRAPHQL),
    (".github/workflows/ci.yml", FileClass.BUILD_SETTING), ("README.md", FileClass.DOCS),
    ("Sources/A/A.docc/A.md", FileClass.DOCS),
])
def test_classify(path, cls):
    assert classify(path) == cls
