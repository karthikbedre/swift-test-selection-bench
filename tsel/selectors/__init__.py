from .base import Selection, Selector
from .package_graph import PackageGraph, RunAll
from .planned import CompilerIndex, HashCache
from .treesitter import TreeSitterSelector

SELECTORS: dict[str, type[Selector]] = {
    "run-all": RunAll,
    "package-graph": PackageGraph,
    "tree-sitter": TreeSitterSelector,
    "compiler-index": CompilerIndex,
    "hash-cache": HashCache,
}

__all__ = ["SELECTORS", "Selection", "Selector"]
