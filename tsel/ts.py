"""Shared Tree-sitter Swift parser."""
from __future__ import annotations

from functools import lru_cache

import tree_sitter_swift
from tree_sitter import Language, Node, Parser


@lru_cache(maxsize=1)
def parser() -> Parser:
    return Parser(Language(tree_sitter_swift.language()))


def parse(src: bytes):
    return parser().parse(src)


def text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text is not None else ""


def walk(node: Node):
    """Depth-first, pre-order, over all nodes."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def string_value(node: Node) -> str | None:
    """Value of a plain string literal node, or None."""
    if node.type != "line_string_literal":
        return None
    parts = [c for c in node.named_children if c.type == "line_str_text"]
    if len(parts) != len(node.named_children):
        return None  # interpolated
    return "".join(text(p) for p in parts)
