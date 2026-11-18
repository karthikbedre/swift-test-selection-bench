"""Approximate Package.swift reader built on Tree-sitter (no Swift toolchain needed)."""
from __future__ import annotations

from tree_sitter import Node

from .graph import DEFAULT_DIRS, Package, Target, _join, _target_id
from .ts import parse, string_value, text, walk

_TARGET_CALLS = {"target": "regular", "executableTarget": "executable", "testTarget": "test",
                 "macro": "macro", "plugin": "plugin", "systemLibrary": "system", "binaryTarget": "binary"}


def _callee(call: Node) -> str | None:
    """`.target(` -> "target"; `Target.target(` -> "target"; `Package(` -> "Package"."""
    head = call.children[0] if call.children else None
    if head is None:
        return None
    if head.type == "simple_identifier":
        return text(head)
    idents = [n for n in walk(head) if n.type == "simple_identifier"]
    return text(idents[-1]) if idents else None


def _args(call: Node) -> dict[str, Node]:
    out: dict[str, Node] = {}
    suffix = next((c for c in call.children if c.type == "call_suffix"), None)
    if suffix is None:
        return out
    va = next((c for c in suffix.children if c.type == "value_arguments"), None)
    if va is None:
        return out
    for arg in va.named_children:
        if arg.type != "value_argument":
            continue
        label = next((c for c in arg.named_children if c.type == "value_argument_label"), None)
        values = [c for c in arg.named_children if c.type != "value_argument_label"]
        if label is not None and values:
            out[text(label)] = values[0]
    return out


def _dep_refs(node: Node, constants: dict[str, Node], depth: int = 0) -> list[tuple[str, str | None]]:
    if depth > 4:
        return []
    refs: list[tuple[str, str | None]] = []
    if node.type == "line_string_literal":
        refs.append(("byName", string_value(node)))
    elif node.type == "call_expression":
        name = _callee(node)
        args = _args(node)
        n = string_value(args["name"]) if "name" in args else None
        if name in ("target", "product", "byName"):
            refs.append((name, n))
    elif node.type == "simple_identifier" and text(node) in constants:
        refs.extend(_dep_refs(constants[text(node)], constants, depth + 1))
    elif node.type in ("array_literal", "additive_expression", "parenthesized_expression"):
        for c in node.named_children:
            refs.extend(_dep_refs(c, constants, depth + 1))
    return refs


def package_from_manifest(source: str, pkg_dir: str) -> Package:
    tree = parse(source.encode())
    root = tree.root_node

    # `let foo: Target.Dependency = .product(...)` and `let deps = [...]` style constants
    constants: dict[str, Node] = {}
    for n in walk(root):
        if n.type == "property_declaration":
            pat = n.child_by_field_name("name")
            values = [c for c in n.named_children if c.type in ("call_expression", "array_literal", "line_string_literal")]
            if pat is not None and values:
                constants[text(pat)] = values[-1]

    targets: dict[str, Target] = {}
    products: dict[str, list[str]] = {}
    pkg_name = pkg_dir
    for n in walk(root):
        if n.type != "call_expression":
            continue
        callee = _callee(n)
        args = _args(n)
        if callee == "Package" and "name" in args:
            pkg_name = string_value(args["name"]) or pkg_name
        elif callee in _TARGET_CALLS and "name" in args:
            name = string_value(args["name"])
            if not name:
                continue
            kind = _TARGET_CALLS[callee]
            sub = string_value(args["path"]) if "path" in args else None
            sub = sub or f"{DEFAULT_DIRS.get(kind, 'Sources')}/{name}"
            refs = _dep_refs(args["dependencies"], constants) if "dependencies" in args else []
            targets[name] = Target(id=_target_id(pkg_dir, name), name=name, package_dir=pkg_dir, kind=kind,
                                   path=_join(pkg_dir, sub), dep_refs=refs)
        elif callee in ("library", "executable") and "name" in args and "targets" in args:
            pname = string_value(args["name"])
            tnames = [string_value(c) for c in args["targets"].named_children if c.type == "line_string_literal"]
            if pname:
                products[pname] = [t for t in tnames if t]
    return Package(dir=pkg_dir, name=pkg_name, targets=targets, products=products, approximate=True)
