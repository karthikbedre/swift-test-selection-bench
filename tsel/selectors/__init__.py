from .base import Selection, Selector
from .package_graph import PackageGraph, RunAll
from .planned import CompilerIndex, HashCache

SELECTORS: dict[str, type[Selector]] = {
    "run-all": RunAll,
    "package-graph": PackageGraph,
    "compiler-index": CompilerIndex,
    "hash-cache": HashCache,
}

__all__ = ["SELECTORS", "Selection", "Selector"]
