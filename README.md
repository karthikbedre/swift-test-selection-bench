# swift-test-selection-bench

An independent benchmark of change-based test selection for Swift: which tests can a change break, and how often is that decision wrong?

When a pull request changes a few files in a codebase split into many Swift packages, most tests cannot be affected, yet continuous integration often runs all of them. This repository measures five ways of choosing the tests to run, on the same pinned commits, and judges each for safety (never skipping a test that would fail), precision (not running tests that could not fail) and overhead (time spent deciding). It publishes the selectors, the harness, trap packages and every result, so tool authors can check their own selectors.

> **Status.** Results from one Apple silicon Mac are complete for four subjects ([report](results/macos/REPORT.md)). Linux runs were a pilot only. Vapor, swift-composable-architecture and swift-syntax, edits made by AI coding agents, and Bazel on public repositories are still to come.

## Contents

- [Research question and hypotheses](#research-question-and-hypotheses)
- [Key findings](#key-findings)
- [Approaches compared](#approaches-compared)
- [Subjects](#subjects)
- [Reproducing the results](#reproducing-the-results)
- [Results and data](#results-and-data)
- [Repository layout](#repository-layout)
- [Threats to validity](#threats-to-validity)
- [Citing](#citing)
- [License](#license)

## Research question and hypotheses

**How do you decide which tests a change can break, and how often is that decision wrong?**

The study began with one hypothesis: a Tree-sitter selector that stays inside the package graph, and falls back to it whenever syntax cannot settle a question, recovers most of the precision of a compiler index at a fraction of the cost. The first results do not support it. Hypotheses H1 to H9, covering edit kind, module depth, Bazel, the cost of the compiler index, commits that select everything, test-class granularity and Swift constructs the compiler records no reference for, are defined in [docs/method.md](docs/method.md#hypotheses).

## Key findings

Measured on an Apple M6 Mac mini (16 GB, macOS 27.0, Xcode 27.2, Swift 6.4.2). Shares are of test targets. A seeded bug is missed when a selector skips every test that catches it.

| Subject | Commits | Package graph | Tree-sitter | Compiler index | Graph runs everything |
|---|---|---|---|---|---|
| swift-argument-parser | 300 | 0.71 | 0.68 | 0.66 | 25% of commits |
| swift-nio | 100 | 0.67 | 0.63 | 0.61 | 38% |
| Hummingbird | 100 | 0.87 | 0.87 | 0.85 | 62% |
| Civitas (controlled edits) | 28 | 0.71 | 0.55 | 0.37 | 11% |

1. **Files that are not Swift dominate.** The package graph runs every test on 25 to 62 percent of real commits, because a continuous integration file, a build setting, the manifest or a file no target owns changed.
2. **On real history the selectors converge at target level.** Tree-sitter and the compiler index choose only a few percent fewer test targets than the package graph. In controlled single edits the compiler index is far more precise.
3. **Tree-sitter rarely narrows.** The names a private or body edit reaches spread through the changed module to common names such as `body`, `register` or `update`, which nearly every dependent spells.
4. **The compiler index pays for its own build.** Net test time saved after its indexed builds: about 800 s over 300 swift-argument-parser commits and 2,400 s over 100 swift-nio commits. Most of its deciding time is the build, which a continuous integration build with indexing on would already cover.
5. **Bazel rebuilds less but reruns the same tests.** After a body edit, Bazel and SwiftPM recompile only the edited module, yet Bazel reruns every dependent test unless the linked binary comes out byte-identical. A new private declaration recompiles every dependent, because test builds export private declarations. Bazel's input hashing selects the same targets as the package graph for source edits and nothing for edits to files that are not build inputs.
6. **Test-class selection helps modestly on real history.** Inside the selected targets, choosing test classes cuts class test time against the package graph by 6 to 27 percent on the three public repositories (more in Civitas's controlled edits), with the compiler index ahead of Tree-sitter in every subject.
7. **Some failures defeat every graph-based selector.** In swift-argument-parser, two seeded bugs were caught only by tests that run a built executable as a separate process with no declared dependency (trap T021). The compiler index also misses a protocol default called through string interpolation (T001) and keys written by synthesized `Codable` code (T002). Tree-sitter catches both.
8. **"Only interface changes matter downstream" is unsafe.** A variant that skips dependents for body and private edits misses seeded bugs in two of four subjects.

Full tables, including deciding time, fallbacks and per-edit results: [results/macos/REPORT.md](results/macos/REPORT.md).

## Approaches compared

| Selector | What decides selection | Unit |
|---|---|---|
| Run everything | Nothing: every test runs | Target |
| Package graph | Test targets that depend on the targets owning the changed files | Target |
| Tree-sitter | Changed names that dependent code spells, bounded by the package graph, with fallbacks for constructs syntax cannot settle | Target and test class |
| Compiler index | Symbol references from an indexed build of the base revision ([`tools/index-query`](tools/index-query)) | Target and test class |
| Bazel hash | Test targets whose input hash changed between base and head, through [target-determinator](https://github.com/bazel-contrib/target-determinator) | Target |
| Interface-only (unsafe on purpose) | Dependents only when a public declaration's signature changed | Target |

How the Tree-sitter selector works, its fallback rules and the safety oracles: [docs/method.md](docs/method.md).

## Subjects

| Subject | Pinned end commit | Why it is here |
|---|---|---|
| [swift-argument-parser](https://github.com/apple/swift-argument-parser) | `d7b6cebecb27` | Small and fast; property wrappers and snapshot fixtures exercise fallbacks |
| [swift-nio](https://github.com/apple/swift-nio) | `b440f7bae889` | Deep graph with one central module |
| [Hummingbird](https://github.com/hummingbird-project/hummingbird) | `5a550f27b0cf` | Mid-size framework with a chain of feature modules |
| Civitas | `7f25fc0307c0` | A 20-module SwiftUI app with 28 single-edit commits by kind and module depth, built for SwiftPM and Bazel ([subjects/civitas](subjects/civitas)) |

All pins and toolchain notes are in [`subjects/subjects.json`](subjects/subjects.json), with reasons in [docs/subjects.md](docs/subjects.md). Civitas comes from [ios-modularization-benchmark](https://github.com/karthikbedre/ios-modularization-benchmark), tree topology only.

## Reproducing the results

Requirements: an Apple silicon Mac with Xcode (27.2 here), Python 3.10 or newer, git, and for the Bazel arm `bazelisk` and the target-determinator binary.

```bash
git clone https://github.com/karthikbedre/swift-test-selection-bench
cd swift-test-selection-bench
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
scripts/build-index-query.sh            # picks the indexstore-db branch that matches swift --version
pytest                                  # all tests pass, none skipped

scripts/run-subject.sh swift-argument-parser 300       # target-level study, resumable
scripts/units-study.py ../subjects/swift-argument-parser results/macos/swift-argument-parser \
    results/macos/swift-argument-parser-classes 60     # test-class pass
scripts/rebuild-study.py ../subjects/civitas 7f25fc0307c08ba759423d03986776c8ac276a84 28 results/macos/civitas-rebuild
scripts/run-traps.py results/macos/traps
scripts/report.py results/macos > results/macos/REPORT.md
```

Step-by-step instructions, expected run times and what each run records: [docs/mac-mini.md](docs/mac-mini.md) and [docs/running.md](docs/running.md). Selection alone needs only Python and git, because files are read from git history:

```bash
tsel select ../swift-nio HEAD~1 HEAD    # what each selector picks for the last commit
```

## Results and data

| Path | Contents |
|---|---|
| [`results/macos/REPORT.md`](results/macos/REPORT.md) | Every table: per subject, commits that select everything, compiler index cost, Civitas edit catalogue, traps, test-class pass |
| `results/macos/<subject>/selections.jsonl` | Per commit and seeded bug: what each selector chose, its rules and its deciding time |
| `results/macos/<subject>/oracle.jsonl` | Per commit and seeded bug: build time, and each test target's result and time |
| `results/macos/<subject>/machine.json` | Machine, toolchain, indexstore-db branch, dependency pins and harness commit |
| `results/macos/<subject>-classes/` | Test-class pass: per-class selections and per-class oracle results |
| `results/macos/civitas-rebuild/rebuild.jsonl` | Per edit: modules Bazel and SwiftPM recompiled, Bazel tests rerun |
| `results/macos/traps/traps.jsonl` | Per trap: validity and each selector's choice |
| [`results/pilot-linux-swift6.0.3/`](results/pilot-linux-swift6.0.3) | Linux pilot, not comparable with the Mac runs |

## Repository layout

```
tsel/                     the package: change reading, package graph, selectors, oracle, seeded bugs, test classes
  selectors/              run-all, package-graph, tree-sitter, compiler-index, interface-only, hash-cache (Bazel)
tools/index-query/        Swift tool on IndexStoreDB that the compiler-index selector calls
subjects/                 pinned subjects, and the Civitas package and edit catalogue
traps/                    trap packages, one Swift construct each
scripts/                  study, test-class pass, rebuild study, traps, report
fixtures/sample-modular/  the worked example from docs/method.md
docs/                     method, running, Mac guide, subjects
results/                  published runs
tests/                    unit tests
```

## Threats to validity

- One machine and one toolchain. Timings are reported as relative comparisons between selectors on the same runs.
- Seeded bugs stand in for real faults, and some subjects have few that any test catches (4 in Civitas, 15 in swift-nio). The only real failures in the Mac runs are two `NIOCoreTests` hangs at real swift-nio commits.
- Civitas edits are synthetic, and the app is built for macOS with a one-file shim for iOS-only SwiftUI modifiers.
- swift-nio needs swift-system pinned to 1.6.6, because it commits no `Package.resolved` and newer swift-system versions clash with its tests.
- About 4 percent of swift-nio class results and 3 percent of Hummingbird's had no matching class in the source reader and are left out for every selector.

More in [docs/method.md](docs/method.md#threats-to-validity).

## Citing

If you use the benchmark, the traps or the results, please cite it. Metadata is in [CITATION.cff](CITATION.cff), and GitHub shows a citation box from it.

Findings are shared with the maintainers of each selector tool before publication.

## License

- **Code** (`tsel/`, `scripts/`, `tools/`, `tests/`, `traps/`, `fixtures/`, `subjects/`): MIT, see [LICENSE](LICENSE). The Civitas sources in `subjects/civitas` come from [ios-modularization-benchmark](https://github.com/karthikbedre/ios-modularization-benchmark), also MIT.
- **Results and documentation** (`results/`, `docs/`): Creative Commons Attribution 4.0 International (CC BY 4.0), see [results/LICENSE](results/LICENSE) and [docs/LICENSE](docs/LICENSE). You may reuse and adapt them with credit.

The subject repositories (swift-argument-parser, swift-nio, Hummingbird) are not included. The harness clones them at their pinned commits, under their own licenses.
