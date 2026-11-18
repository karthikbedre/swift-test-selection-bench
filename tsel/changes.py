"""Read a change between two revisions and sort the changed files into classes.

Every selector starts from the same ChangeSet, so differences in selection come
from the selectors and never from how the diff was read.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath


class FileClass(str, Enum):
    SWIFT_SOURCE = "swift_source"
    SWIFT_TEST = "swift_test"
    MANIFEST = "manifest"          # Package.swift, Package.resolved, Project.swift, *.xcodeproj
    BUILD_SETTING = "build_setting"  # .xcconfig, .xctestplan, CI config, toolchain pins
    RESOURCE = "resource"          # fixtures, snapshots, assets, json, strings
    GRAPHQL = "graphql"
    DOCS = "docs"                  # markdown, DocC catalogs, licenses
    OTHER = "other"


@dataclass
class FileChange:
    path: str
    status: str                    # A, M, D, R
    old_path: str | None = None    # set for renames
    file_class: FileClass = FileClass.OTHER
    old_lines: list[tuple[int, int]] = field(default_factory=list)  # changed ranges, 1-based inclusive
    new_lines: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class ChangeSet:
    repo: str
    base: str
    head: str
    files: list[FileChange]

    def by_class(self, cls: FileClass) -> list[FileChange]:
        return [f for f in self.files if f.file_class == cls]


_MANIFEST_NAMES = {"Package.swift", "Package.resolved", "Project.swift", "Workspace.swift", "Tuist.swift"}
_BUILD_SUFFIXES = {".xcconfig", ".xctestplan", ".xcscheme", ".pbxproj", ".entitlements", ".plist"}
_RESOURCE_SUFFIXES = {".json", ".png", ".jpg", ".jpeg", ".pdf", ".svg", ".strings", ".stringsdict",
                      ".xcstrings", ".txt", ".yaml", ".yml", ".xml", ".html", ".bin", ".dat", ".xcassets",
                      ".colorset", ".imageset", ".storyboard", ".xib"}
_DOC_SUFFIXES = {".md", ".markdown", ".rst", ".docc", ".tutorial"}
_DOC_NAMES = {"LICENSE", "LICENSE.txt", "NOTICE", "NOTICE.txt", "CODEOWNERS", "CONTRIBUTORS.txt", ".gitignore",
              ".spi.yml", ".mailmap"}


def classify(path: str, test_dirs: tuple[str, ...] = ("Tests",)) -> FileClass:
    p = PurePosixPath(path)
    parts = p.parts
    if p.name in _MANIFEST_NAMES or p.name.startswith("Package@swift") or ".xcodeproj" in path or ".xcworkspace" in path:
        return FileClass.MANIFEST
    if any(part in (".github", ".circleci", ".buildkite") for part in parts) or p.name in (
            ".swift-version", ".swiftformat", ".swift-format", ".swiftlint.yml", "Makefile", "Dangerfile.swift"):
        return FileClass.BUILD_SETTING
    if p.suffix in _BUILD_SUFFIXES:
        return FileClass.BUILD_SETTING
    if p.name in _DOC_NAMES or p.suffix.lower() in _DOC_SUFFIXES or any(part.endswith(".docc") for part in parts):
        return FileClass.DOCS
    if p.suffix in (".graphql", ".graphqls", ".gql"):
        return FileClass.GRAPHQL
    if p.suffix == ".swift":
        if parts and parts[0] in test_dirs:
            return FileClass.SWIFT_TEST
        return FileClass.SWIFT_SOURCE
    if p.suffix.lower() in _RESOURCE_SUFFIXES or any(part.endswith((".xcassets", ".bundle")) or part in (
            "Resources", "Fixtures", "__Snapshots__") for part in parts):
        return FileClass.RESOURCE
    return FileClass.OTHER


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-c", "core.quotePath=false", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _ranges(start: int, count: int) -> tuple[int, int] | None:
    if count == 0:
        # Pure insertion or deletion: the change sits between `start` and `start + 1`.
        return (max(start, 1), max(start, 1))
    return (start, start + count - 1)


def read_changes(repo: str, base: str, head: str) -> ChangeSet:
    """Diff base..head with zero context and record changed line ranges on both sides."""
    files: list[FileChange] = []
    for line in _git(repo, "diff", "--name-status", "-M", base, head).splitlines():
        cols = line.split("\t")
        status = cols[0][0]
        if status == "R":
            files.append(FileChange(path=cols[2], old_path=cols[1], status="R"))
        else:
            files.append(FileChange(path=cols[1], status=status))

    by_path = {f.path: f for f in files}
    current: FileChange | None = None
    minus_path: str | None = None
    for line in _git(repo, "diff", "-U0", "-M", "--no-color", base, head).splitlines():
        if line.startswith("diff --git "):
            current, minus_path = None, None
        elif line.startswith("--- "):
            # git appends a tab after paths that contain spaces
            minus_path = line[6:].rstrip("\t") if line.startswith("--- a/") else None
        elif line.startswith("+++ "):
            if line.startswith("+++ b/"):
                current = by_path.get(line[6:].rstrip("\t"))
            elif minus_path is not None:  # deleted file: key it by its old path
                current = by_path.get(minus_path)
        elif line.startswith("@@") and current is not None:
            m = _HUNK.match(line)
            if m:
                o = _ranges(int(m.group(1)), int(m.group(2) or 1))
                n = _ranges(int(m.group(3)), int(m.group(4) or 1))
                if o:
                    current.old_lines.append(o)
                if n:
                    current.new_lines.append(n)

    for f in files:
        f.file_class = classify(f.path)
    return ChangeSet(repo=repo, base=base, head=head, files=files)


def file_at(repo: str, rev: str, path: str) -> bytes | None:
    try:
        return subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"], check=True,
                              capture_output=True).stdout
    except subprocess.CalledProcessError:
        return None
