# swift-test-selection-bench

An independent benchmark of change-based test selection for Swift.

When a pull request changes a few files in a codebase split into many Swift packages, most tests cannot be affected, yet CI often runs all of them. Selective testing runs only the tests a change can break. This repository asks one question:

> **How do you decide which tests a change can break, and how often is that decision wrong?**

It compares five ways of deciding on the same real commits, and publishes the selectors, the harness and a set of trap packages so tool authors can check their own selectors.

## The five approaches

| Approach | What decides selection | Setup cost | Status here |
|---|---|---|---|
| Run everything | Nothing; every test runs | None | Done |
| Hash-based caching | A changed fingerprint of a test target's inputs (Tuist, Bazel) | Low where the build already uses them | Planned (macOS, supported subjects only) |
| Package graph | Test targets that depend on the targets owning the changed files | Low | Done |
| Tree-sitter syntax selector | Changed names that dependent code spells, bounded by the package graph | Moderate; no build, no Swift toolchain | First version done |
| Compiler index | Symbol references recorded by the compiler during an indexed build | High; full build with indexing | First version done (macOS and Linux) |

Three words carry the evaluation:

- **Safe:** never skips a test that would have failed.
- **Precise:** does not run tests that could not have failed.
- **Overhead:** time spent deciding, counted in end-to-end time.

## Hypothesis

A Tree-sitter selector that stays inside the package graph, and falls back to it whenever syntax cannot settle a question, recovers most of the precision of a compiler index at a fraction of the setup cost, without missing failures the package graph would catch.

## How the Tree-sitter selector works

1. Map each changed line to the smallest declaration around it, in both the old and the new file, so renamed and deleted names count.
2. Sort the change: comment or formatting only, an edit inside a declaration, an added or removed declaration or conformance, or a stored-property change.
3. Turn it into changed names. Members Swift calls on its own (`description`, `body`, `hash(into:)`, `encode(to:)`, `CodingKeys`, initializers) widen to their owning type. Protocol and protocol-extension members widen to every conforming type. Inside the changed target, any declaration that uses a changed name is changed too, until nothing new is added.
4. A target that spells a changed name is affected, and so is every target that depends on it (the chain rule).
5. Fall back to the package graph whenever syntax cannot settle the question: macros and macro-like attributes, custom operators, property wrappers, result builders, conditional compilation, top-level code, line-sensitive files and code that does not parse.

The answer is always a subset of the package-graph answer: it can narrow it, never widen it. Every fallback is recorded, so the fallback rate is a result in its own right.

## How safety is judged

- **Real failures:** fail-then-pass commits from each project's public CI history, re-run locally.
- **Seeded failures:** mutants in each commit's changed files, plus hand-written ones at risky spots such as protocol defaults, coding keys and fixture keys.
- **Trap failures:** small packages in [`traps/`](traps/), each with one Swift trap and one test that must be selected. Third-party selectors run on them as black boxes.

Failures are re-run before a miss is called unsafe, because flaky tests look like misses. A run of zero tests counts as a harness failure.

Full protocol: [docs/method.md](docs/method.md).

## Subjects

Six public Swift packages plus one sample iOS app, pinned in [`subjects/subjects.json`](subjects/subjects.json): swift-nio, swift-syntax, swift-argument-parser, Hummingbird, Vapor and swift-composable-architecture. Reasons for each are in [docs/subjects.md](docs/subjects.md).

## Quick start

Selection needs only Python 3.10+ and git, because files are read from git history and parsed with Tree-sitter.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                                   # selector behaviour on fixtures and traps

git clone https://github.com/apple/swift-nio ../swift-nio
tsel select ../swift-nio HEAD~1 HEAD     # what each selector picks for the last commit
tsel replay ../swift-nio --count 300 --out results/swift-nio/selections.jsonl
```

Running tests needs the subject's Swift toolchain (a Linux container or macOS):

```bash
tsel oracle ../swift-nio <commit> --out results/swift-nio/oracle.jsonl
tsel score results/swift-nio/selections.jsonl results/swift-nio/oracle.jsonl --csv results/swift-nio/scores.csv
```

Full steps, including what still needs a Mac: [docs/running.md](docs/running.md).

When `swift` is on `PATH`, the package graph comes from `swift package dump-package`. Without it, a Tree-sitter reader of `Package.swift` is used and results are marked approximate.

## Layout

```
tsel/
  changes.py            diff base..head, changed line ranges, file classes
  graph.py, manifest.py package graph (toolchain or Tree-sitter manifest reader)
  swiftdecl.py          declarations, spelled names, conformances, risky constructs
  selectors/            run-all, package-graph, tree-sitter, compiler-index, planned hash-cache
  replay.py             selections over a commit range
  oracle.py             run every test target at a revision, re-run failures
  score.py              misses, selected share, time saved
  mutate.py             seeded bugs on the lines a commit changed
fixtures/sample-modular/  the worked example from docs/method.md
traps/                    trap packages, one Swift trap each
subjects/subjects.json    pinned subjects
tools/index-query/        Swift tool on IndexStoreDB that the compiler-index selector calls
scripts/                  study run (real commits plus seeded bugs) and its scoring
results/                  published runs, one folder per subject
tests/                    unit tests
```

## Status

- Working: change reading, both package-graph loaders, run-all, package-graph, Tree-sitter and compiler-index selectors, replay, oracle runner, scoring, first trap, seeded bugs, a first full run on swift-argument-parser ([results](results/swift-argument-parser/README.md)).
- Next: test-file level selection for subjects with few large test targets, SwiftParser variant of the syntax selector, mutation runs, the full trap set, hash-based caching on the sample app.

Findings will be shared with the maintainers of each selector tool before publication.

## License

MIT. See [LICENSE](LICENSE).
