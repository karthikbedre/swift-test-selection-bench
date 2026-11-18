"""Seeded faults: small mutants on the lines a commit changed.

A lightweight stand-in for Muter that runs anywhere git and Python run. Each mutant is a commit on
top of the original head, so a selector sees base..mutant as one change that both made the commit's
edit and introduced the fault. The oracle then says which test targets catch it.
"""
from __future__ import annotations

import re
import subprocess

from .changes import FileClass, read_changes

# (name, pattern, replacement). Applied to one occurrence on one changed line.
OPERATORS = [
    ("eq-to-ne", re.compile(r"(?<![=!<>])==(?!=)"), "!="),
    ("ne-to-eq", re.compile(r"!=(?!=)"), "=="),
    ("and-to-or", re.compile(r"&&"), "||"),
    ("or-to-and", re.compile(r"\|\|"), "&&"),
    ("true-to-false", re.compile(r"\btrue\b"), "false"),
    ("false-to-true", re.compile(r"\bfalse\b"), "true"),
    ("lt-to-le", re.compile(r"(?<=\s)<(?=\s)"), "<="),
    ("gt-to-ge", re.compile(r"(?<=\s)>(?=\s)"), ">="),
    ("plus-one", re.compile(r"\+ 1\b"), "+ 2"),
    ("minus-one", re.compile(r"- 1\b"), "- 2"),
    ("string-literal", re.compile(r'"([A-Za-z][^"\\]{0,40})"'), r'"\1_"'),
    ("drop-not", re.compile(r"(?<![!=])!(?=[A-Za-z(])"), ""),
]

SKIP_LINE = re.compile(r"^\s*(//|/\*|\*|import\b|#|@)")


def _git(repo: str, *args: str, input: str | None = None) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True,
                          input=input).stdout.strip()


def candidates(repo: str, base: str, head: str) -> list[tuple[str, int, str, str, str]]:
    """(path, line number, operator, old line, new line) for each changed source line that mutates."""
    out = []
    for f in read_changes(repo, base, head).files:
        if f.file_class != FileClass.SWIFT_SOURCE or f.status == "D":
            continue
        lines = _git(repo, "show", f"{head}:{f.path}").split("\n")
        for a, b in f.new_lines:
            for n in range(a, b + 1):
                if n - 1 >= len(lines):
                    continue
                text = lines[n - 1]
                if SKIP_LINE.match(text) or not text.strip():
                    continue
                for name, pat, rep in OPERATORS:
                    if pat.search(text):
                        out.append((f.path, n, name, text, pat.sub(rep, text, count=1)))
                        break
    return out


def make_mutant(repo: str, head: str, path: str, line: int, new_text: str, message: str) -> str:
    """Commit one changed line on top of `head` without touching any checkout. Returns the commit."""
    lines = _git(repo, "show", f"{head}:{path}").split("\n")
    lines[line - 1] = new_text
    blob = _git(repo, "hash-object", "-w", "--stdin", input="\n".join(lines))
    tree = _git(repo, "rev-parse", f"{head}^{{tree}}")
    env_idx = {"GIT_INDEX_FILE": f"/tmp/tsel-mutant-index-{head[:12]}"}
    run = lambda *a, **k: subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True, text=True,
                                         env={**__import__("os").environ, **env_idx}, **k).stdout.strip()
    run("read-tree", tree)
    mode = _git(repo, "ls-tree", head, "--", path).split()[0]
    run("update-index", "--cacheinfo", f"{mode},{blob},{path}")
    new_tree = run("write-tree")
    return run("-c", "user.name=tsel", "-c", "user.email=tsel@example.invalid", "commit-tree", new_tree,
               "-p", head, "-m", message)
