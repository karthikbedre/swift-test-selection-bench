"""Selectors not built yet. The interface is fixed; the implementation lands with the runs that need it.

HashCache
    Target-level fingerprints of each test target's inputs, as Tuist's selective testing and Bazel do.
    Run only on subjects that already build with Tuist or Bazel (the sample app is set up with Tuist).
"""
from __future__ import annotations

from ..changes import ChangeSet
from ..graph import Graph
from .base import Selection, Selector


class HashCache(Selector):
    name = "hash-cache"

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        raise NotImplementedError("hash-cache runs through Tuist or Bazel on supported subjects; see module docstring")
