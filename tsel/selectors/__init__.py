from .base import Selection, Selector
from .package_graph import PackageGraph, RunAll
from .compiler_index import CompilerIndex
from .interface_only import InterfaceOnly
from .hash_cache import HashCache
from .treesitter import TreeSitterSelector

SELECTORS: dict[str, type[Selector]] = {
    "run-all": RunAll,
    "package-graph": PackageGraph,
    "tree-sitter": TreeSitterSelector,
    "compiler-index": CompilerIndex,
    "interface-only": InterfaceOnly,
    "hash-cache": HashCache,
}

__all__ = ["SELECTORS", "Selection", "Selector"]
