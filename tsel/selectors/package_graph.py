"""Baselines: run everything, and target-level selection over the package graph."""
from __future__ import annotations

from ..changes import ChangeSet
from ..graph import Graph
from .base import Selection, Selector, route


class RunAll(Selector):
    name = "run-all"

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        return Selection(self.name, graph.test_targets(), all_tests=True)


class PackageGraph(Selector):
    """Run every test target that depends, directly or not, on a target owning a changed file."""
    name = "package-graph"

    def _select(self, changes: ChangeSet, graph: Graph) -> Selection:
        r = route(changes, graph)
        if r.all_tests_reasons:
            return Selection(self.name, graph.test_targets(), all_tests=True, rules=r.all_tests_reasons)
        origins = set(r.source_changes) | set(r.coarse_origins)
        tests = self.graph_tests(graph, origins) | r.test_targets
        rules = [f"graph:{o}" for o in sorted(origins)]
        return Selection(self.name, tests, rules=rules)
