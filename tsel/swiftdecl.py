"""Syntax facts about one Swift file: declarations, spelled names, conformances and risky constructs."""
from __future__ import annotations

from dataclasses import dataclass, field

from tree_sitter import Node

from .ts import parse, text, walk

TYPE_KEYWORDS = ("struct", "class", "enum", "actor", "extension")
MEMBER_NODES = {
    "function_declaration": "func", "property_declaration": "var", "init_declaration": "init",
    "deinit_declaration": "deinit", "subscript_declaration": "subscript", "typealias_declaration": "typealias",
    "enum_entry": "case", "protocol_function_declaration": "func", "protocol_property_declaration": "var",
    "associatedtype_declaration": "associatedtype", "macro_declaration": "macro",
    "operator_declaration": "operator", "precedence_group_declaration": "precedencegroup",
}

# Members Swift calls without the caller spelling their name. A change to one widens to its owning type.
IMPLICIT_MEMBERS = {
    "description", "debugDescription", "customMirror", "playgroundDescription", "body", "makeBody",
    "hash", "hashValue", "encode", "CodingKeys", "rawValue", "allCases", "makeIterator", "next",
    "makeAsyncIterator", "callAsFunction", "subscript", "wrappedValue", "projectedValue", "id",
    "errorDescription", "failureReason", "recoverySuggestion", "localizedDescription",
    "init", "deinit", "buildBlock", "buildExpression", "buildOptional", "buildEither", "buildArray",
    "buildPartialBlock", "buildFinalResult", "dynamicMember",
}
# Attributes that never generate code. Any other attribute on a changed declaration may be a
# macro or a property wrapper, so the selector falls back to the package graph.
INERT_ATTRIBUTES = {
    "available", "MainActor", "objc", "nonobjc", "discardableResult", "inlinable", "usableFromInline",
    "inline", "frozen", "testable", "escaping", "Sendable", "unchecked", "preconcurrency",
    "_spi", "_implementationOnly", "warn_unqualified_access", "IBAction", "IBOutlet", "IBInspectable",
    "IBDesignable", "NSManaged", "GKInspectable", "autoclosure", "noescape", "_disfavoredOverload",
    "_alwaysEmitIntoClient", "derivative", "transpose", "convention", "isolated", "globalActor",
    "nonisolated", "retroactive", "backDeployed", "_silgen_name", "_cdecl", "_effects", "_transparent",
    "_specialize", "_semantics", "_optimize", "_marker", "_eagerMove", "_noEagerMove", "_lexicalLifetimes",
    "Test", "Suite",  # swift-testing markers in test files
}
RISKY_ATTRIBUTES = {"propertyWrapper", "resultBuilder", "dynamicMemberLookup", "dynamicCallable",
                    "_exported", "main", "UIApplicationMain", "NSApplicationMain"}
LINE_SENSITIVE = ("#line", "#file", "#fileID", "#filePath", "#column", "#function", "#sourceLocation")


@dataclass
class Decl:
    kind: str                   # struct/class/enum/actor/extension/protocol/func/var/init/...
    name: str
    owner: str | None           # enclosing type or extended type name
    owner_kind: str | None      # kind of the enclosing declaration
    start: int                  # 1-based line
    end: int
    attributes: list[str] = field(default_factory=list)
    inherits: list[str] = field(default_factory=list)   # for type declarations and extensions
    stored: bool = False        # stored property (no accessor body)
    in_conditional: bool = False  # sits inside #if
    uses: set[str] = field(default_factory=set)  # names this declaration spells (type headers only for types)

    @property
    def key(self) -> tuple[str, str | None, str]:
        return (self.kind, self.owner, self.name)


@dataclass
class FileFacts:
    decls: list[Decl]
    spelled: set[str]
    has_error: bool
    error_lines: list[tuple[int, int]]     # line spans of ERROR and MISSING nodes
    leaf_signature: list[tuple[str, str]]
    risky: list[str]                       # file-level risky constructs, with line numbers
    line_sensitive: bool
    protocols: set[str]
    conformances: dict[str, set[str]]      # type name -> inherited/conformed names


def _first_keyword(node: Node) -> str | None:
    for c in node.children:
        if not c.is_named and c.type in TYPE_KEYWORDS:
            return c.type
    return None


def _decl_name(node: Node) -> str:
    n = node.child_by_field_name("name")
    if n is not None:
        return text(n)
    if node.type == "init_declaration":
        return "init"
    if node.type == "deinit_declaration":
        return "deinit"
    if node.type == "subscript_declaration":
        return "subscript"
    if node.type == "operator_declaration":
        op = next((c for c in node.named_children if c.type == "custom_operator"), None)
        return text(op) if op is not None else "operator"
    if node.type == "enum_entry":
        ids = [c for c in node.named_children if c.type == "simple_identifier"]
        return ",".join(text(i) for i in ids) or "case"
    ident = next((c for c in node.named_children if c.type in ("simple_identifier", "type_identifier")), None)
    return text(ident) if ident is not None else node.type


def _attributes(node: Node) -> list[str]:
    out = []
    mods = next((c for c in node.children if c.type == "modifiers"), None)
    for scope in ([mods] if mods is not None else []) + [node]:
        for c in scope.children:
            if c.type == "attribute":
                ut = next((x for x in walk(c) if x.type in ("type_identifier", "simple_identifier")), None)
                if ut is not None:
                    out.append(text(ut))
    return out


def _inherits(node: Node) -> list[str]:
    out = []
    for c in node.children:
        if c.type == "inheritance_specifier":
            ids = [x for x in walk(c) if x.type == "type_identifier"]
            if ids:
                out.append(text(ids[-1]))
    return out


def _names_in(node: Node) -> set[str]:
    return {text(n) for n in walk(node) if n.type in ("simple_identifier", "type_identifier")}


def _header_names(node: Node) -> set[str]:
    out: set[str] = set()
    for c in node.children:
        if c.type in ("inheritance_specifier", "attribute", "modifiers", "type_constraints"):
            out |= _names_in(c)
    return out


def _within_directive(node: Node) -> bool:
    """True when a sibling `#if` directive opens before this node and has not closed."""
    parent = node.parent
    while parent is not None:
        depth = 0
        for c in parent.children:
            if c.id == node.id:
                break
            if c.type == "directive":
                t = text(c).strip()
                if t.startswith("#if"):
                    depth += 1
                elif t.startswith("#endif"):
                    depth = max(0, depth - 1)
        if depth > 0:
            return True
        node, parent = parent, parent.parent
    return False


def analyze(src: bytes) -> FileFacts:
    tree = parse(src)
    root = tree.root_node
    decls: list[Decl] = []
    protocols: set[str] = set()
    conformances: dict[str, set[str]] = {}
    risky: list[str] = []

    def visit(node: Node, owner: str | None, owner_kind: str | None) -> None:
        for c in node.named_children:
            if c.type == "class_declaration":
                kind = _first_keyword(c) or "type"
                name = _decl_name(c)
                inh = _inherits(c)
                conformances.setdefault(name, set()).update(inh)
                d = Decl(kind=kind, name=name, owner=owner, owner_kind=owner_kind,
                         start=c.start_point[0] + 1, end=c.end_point[0] + 1,
                         attributes=_attributes(c), inherits=inh, in_conditional=_within_directive(c),
                         uses=_header_names(c))
                decls.append(d)
                body = next((x for x in c.named_children if x.type in ("class_body", "enum_class_body")), None)
                if body is not None:
                    visit(body, name, kind)
            elif c.type == "protocol_declaration":
                name = _decl_name(c)
                protocols.add(name)
                inh = _inherits(c)
                conformances.setdefault(name, set()).update(inh)
                decls.append(Decl(kind="protocol", name=name, owner=owner, owner_kind=owner_kind,
                                  start=c.start_point[0] + 1, end=c.end_point[0] + 1,
                                  attributes=_attributes(c), inherits=inh, in_conditional=_within_directive(c),
                                  uses=_header_names(c)))
                body = next((x for x in c.named_children if x.type == "protocol_body"), None)
                if body is not None:
                    visit(body, name, "protocol")
            elif c.type in MEMBER_NODES:
                kind = MEMBER_NODES[c.type]
                stored = c.type == "property_declaration" and not any(
                    x.type in ("computed_property", "protocol_property_requirements") for x in c.named_children)
                d = Decl(kind=kind, name=_decl_name(c), owner=owner, owner_kind=owner_kind,
                         start=c.start_point[0] + 1, end=c.end_point[0] + 1,
                         attributes=_attributes(c), stored=stored, in_conditional=_within_directive(c),
                         uses=_names_in(c))
                decls.append(d)
                if c.type == "enum_entry":
                    continue
            elif c.type in ("directive",):
                continue
            elif c.type not in ("comment", "multiline_comment"):
                # statements, nested blocks under #if, etc.
                if c.type in ("class_body", "enum_class_body", "protocol_body"):
                    visit(c, owner, owner_kind)

    visit(root, None, None)

    spelled: set[str] = set()
    leaves: list[tuple[str, str]] = []
    line_sensitive = False
    for n in walk(root):
        if n.type in ("simple_identifier", "type_identifier"):
            spelled.add(text(n))
        if n.child_count == 0 and n.type not in ("comment", "multiline_comment"):
            leaves.append((n.type, text(n)))
        if n.type in ("macro_invocation",) or (n.type == "directive" and False):
            risky.append(f"macro use at line {n.start_point[0] + 1}")
        if n.type == "operator_declaration":
            risky.append(f"custom operator at line {n.start_point[0] + 1}")
    src_text = src.decode("utf-8", errors="replace")
    line_sensitive = any(tok in src_text for tok in LINE_SENSITIVE)
    # Swift spells operator implementations as names in leaves too: keep them for matching.
    for n in walk(root):
        if n.type in ("custom_operator",):
            spelled.add(text(n))

    error_lines = [(n.start_point[0] + 1, n.end_point[0] + 1) for n in walk(root) if n.type == "ERROR" or n.is_missing]
    return FileFacts(decls=decls, spelled=spelled, has_error=root.has_error, error_lines=error_lines,
                     leaf_signature=leaves,
                     risky=risky, line_sensitive=line_sensitive, protocols=protocols, conformances=conformances)


def innermost(decls: list[Decl], start: int, end: int) -> list[Decl]:
    """Smallest declarations that contain or overlap the line range [start, end]."""
    hits = [d for d in decls if d.start <= end and d.end >= start]
    if not hits:
        return []
    # Keep a hit only if no other hit sits strictly inside it.
    out = []
    for d in hits:
        if not any(o is not d and o.start >= d.start and o.end <= d.end and (o.start, o.end) != (d.start, d.end)
                   for o in hits):
            out.append(d)
    return out


def macro_like(attrs: list[str]) -> list[str]:
    return [a for a in attrs if a not in INERT_ATTRIBUTES]
