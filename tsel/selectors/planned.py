"""Selectors that need macOS and a Swift toolchain. Interfaces are fixed; implementations land with the Mac runs.

CompilerIndex
    1. Build the base revision with indexing on:
       ``swift build --build-tests -Xswiftc -index-store-path -Xswiftc <dir>/index``
       (Xcode projects: ``xcodebuild build-for-testing`` with ``COMPILER_INDEX_STORE_ENABLE=YES``).
    2. For each changed declaration (same step 1-2 as the Tree-sitter selector, so both start from the
       same changed symbols), look up its USR and every occurrence that refers to it, using IndexStoreDB
       through a small Swift helper in ``tools/index-query`` (to be written).
    3. Map each referring file to its target, apply the chain rule, intersect with the package graph.
    Known blind spots to record, not fix: code the compiler synthesizes (Codable, Equatable, Hashable)
    and branches outside the built configuration.

HashCache
    Target-level fingerprints of each test target's inputs, as Tuist's selective testing and Bazel do.
    Run only on subjects that already build with Tuist or Bazel (the sample app is set up with Tuist).
"""
from __future__ import annotations

from ..changes import ChangeSet
from ..graph import Graph
from .base import Selection, Selector


class CompilerIndex(Selector):
    name = "compiler-index"

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        raise NotImplementedError("compiler-index needs macOS, a Swift toolchain and tools/index-query; see module docstring")


class HashCache(Selector):
    name = "hash-cache"

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        raise NotImplementedError("hash-cache runs through Tuist or Bazel on supported subjects; see module docstring")
