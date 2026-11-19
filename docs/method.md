# Method

## Research question

How do you decide which tests a change can break, and how often is that decision wrong?

The contribution is an independent yardstick, not one more selector: five approaches measured on the same pinned commits, judged for safety three ways, with every fallback counted.

## Definitions

- **Selector:** given a base and a head revision, returns a set of tests to run.
- **Safe:** for every commit, every test that fails at head (and is not flaky) is selected.
- **Precise:** few selected tests could not have failed. Measured as the share of test targets selected, and as the share of selected tests with no path to any failure or mutant.
- **Overhead:** wall time to decide, including any build the selector needs before it can decide.
- **End-to-end time:** overhead + build of what runs + test time of what runs.

## Unit of selection

Test targets first, because that is what CI systems run and what every approach can express. A second pass selects test classes inside the selected targets.

### Test-class pass

The target-level runs showed the selectors converging wherever a hub module sits under most test targets (H6). The second pass asks whether they diverge one level down.

- **Unit.** A test class: an `XCTestCase` subclass, or a swift-testing suite (a type holding `@Test` functions, with or without `@Suite`). A type extended across files is one unit. Top-level `@Test` functions in a target form one unit per target.
- **Oracle.** Each selected test target still runs once, alone. Per-test results come from the swift-testing XML report (`--xunit-output`) and from XCTest's console lines, which this SwiftPM does not write to XML. A unit fails when any of its tests fails. A seeded bug's killers are the units that fail with it and pass without it.
- **Run everything, package graph, Bazel hash and interface-only** cannot see inside a target, so they select every unit of the targets they select.
- **Tree-sitter.** Inside each selected test target, the changed names are first spread through the target's helper declarations (fixtures, extensions, shared setup) until nothing new is added. A unit is selected when one of its files spells one of those names. A target reached only through the chain rule, without spelling any changed name itself, keeps all its units, and that is recorded as a fallback.
- **Compiler index.** A unit is selected when one of its files appears among the files that refer to the changed declarations, spread through the target's helper files the same way. Targets reached only through the chain rule keep all their units.
- **Commits.** Only commits and seeded bugs where the package graph did not run everything: the pass measures what finer selection adds where target selection already narrowed.
- **Measures.** Share of units selected, test time of the selected units, units missed per seeded bug, and the share of selected targets where finer selection fell back to all units.

## Change reading (shared by all selectors)

Each commit is compared with its first parent. Changed files are sorted into classes, each with one rule:

| Class | Examples | Rule |
|---|---|---|
| Swift source | `Sources/**.swift` | selector-specific |
| Swift test | `Tests/**.swift` | that test target runs |
| Manifest | `Package.swift`, `Package.resolved`, `.xcodeproj` | everything runs |
| Build setting | `.xcconfig`, `.xctestplan`, CI config, toolchain pins | everything runs |
| Resource | fixtures, snapshots, assets, string catalogs | owning target's dependents (key matching planned) |
| GraphQL | `.graphql` operations and schema | owning target's dependents (generated-type mapping planned) |
| Docs | Markdown, DocC, license | nothing runs |
| Unowned | a file no target owns | everything runs, unless it sits in a separate nested package |

## Selectors

1. **Run everything.** Baseline for safety and time.
2. **Hash-based caching (Bazel).** Every target's inputs are hashed at base and head, and test targets whose hash changed are selected, using an existing tool (`bazel-diff` or `target-determinator`). See "Bazel arm" below.
3. **Package graph.** Owning targets of changed files, then every test target that depends on them directly or indirectly. The graph comes from `swift package dump-package`, or from a Tree-sitter reader of `Package.swift` when no toolchain is present.
4. **Tree-sitter syntax selector.** See the README for the five steps. Escalation rules, which carry most of the research contribution:
   - Members Swift calls without the caller spelling them widen to the owning type: `description`, `debugDescription`, `body`, `hash(into:)`, `==`, `encode(to:)`, `init(from:)`, `CodingKeys`, `rawValue`, `makeIterator`, `callAsFunction`, `id`, `wrappedValue`, result-builder methods and initializers.
   - Stored-property changes widen to the owning type (memberwise init, synthesized `Codable`, `Equatable`, `Hashable`).
   - Protocol requirements and protocol-extension members widen to the protocol and every conforming type, following refinement.
   - Inside the changed target, a declaration that uses a changed name is itself changed, until nothing new is added.
   - Fallback to the package graph for: macro declarations and uses, any attribute that may generate code, custom operators and precedence groups, `@propertyWrapper`, `@resultBuilder`, `@dynamicMemberLookup`, `@dynamicCallable`, `@_exported`, changes under `#if`, top-level code and imports, line-sensitive files (`#line`, `#file`, `#function` and similar) for formatting-only edits, and parse errors that touch the changed declarations.
   - The answer is intersected with the package-graph answer.
   - A variant runs the same rules on SwiftParser, with and without its name lookup, to separate parser mistakes from the limits of syntax alone.
5. **Compiler index.** Build the base revision with indexing on, map the changed lines to declarations exactly as the Tree-sitter selector does, look up their USRs in IndexStoreDB (`tools/index-query`), follow references inside the changed module to the declarations that contain them, map referring files to targets, apply the chain rule and intersect with the package graph. Changes under `#if` and declarations the index does not hold fall back to the package graph. Blind spots are recorded, not patched: implicit calls with no recorded reference (trap T001, where the plain index lookup skips the failing test), compiler-synthesized conformances and code outside the built configuration.

6. **Interface-only (a deliberately unsafe variant).** Selects the changed target's own tests, and its dependents' tests only when a change touches a public or open declaration's signature. Body edits and private or internal declarations never reach dependents. It states the common intuition that only interface changes matter downstream, so its missed seeded bugs measure what that intuition costs.

## Hypotheses

H1 to H3 come from the study's starting question. H4 to H9 were added once the pilot showed where the selectors agree.

| | Hypothesis | Measured on | What would refute it |
|---|---|---|---|
| H1 | The package graph runs every downstream test target for any edit to a module, whatever the edit kind. | Civitas, all subjects | (holds by construction; the baseline) |
| H2 | Tree-sitter selects a downstream test target only when it spells a name the edit reaches. On private and body edits it selects fewer targets than the graph, with no missed seeded bugs. | Civitas edit catalogue | Equal shares on private and body edits, or misses |
| H2b | The interface-only variant selects fewest targets but misses seeded bugs on body edits. | Civitas edit catalogue | No misses |
| H3 | Bazel recompiles downstream modules only when a module's compiled interface (`.swiftmodule`) changes, but reruns every downstream test target on any source edit, because test binaries link the changed object files. It selects fewer targets than the graph only on edits to files that are not build inputs. | Civitas, Bazel execution log | Downstream tests skipped after a body edit |
| H4 | Almost all of the compiler index's deciding time is its indexed build. When the index comes from a build CI runs anyway, its added cost is the indexing overhead plus the query, which is small. | Civitas, swift-argument-parser | Indexing overhead close to a full build |
| H5 | Commits that touch only CI, scripts, build settings or unowned files are common, and at target level they erase any gain from name-level selection. Bazel's input hashing ignores most of them. | All subjects | Small share of such commits |
| H6 | Where a hub module sits under most test targets, selectors agree at target level and differ at test-class level. | swift-nio, Vapor, swift-composable-architecture | No divergence at class level |
| H7 | The deeper the edited module sits in the graph, the larger the gap between the graph and the name-level selectors. | Civitas, edits at core, hub, middle and leaf modules | Gap independent of depth |
| H8 | Comment-only and formatting-only edits select the same targets as body edits for the graph and Bazel, and nothing downstream for Tree-sitter and the compiler index. | Civitas edit catalogue | Name-level selectors select downstream |
| H9 | Constructs the compiler records no reference for (implicit `description`, synthesized `Codable`, `Equatable` and `Hashable`) are where the compiler index is unsafe and Tree-sitter's widening rules are not. | Traps T001 to T004 | Index catches them |

## Controlled subject: Civitas

Real history mixes edit kinds and rarely isolates one. Civitas, the generated city-services app from the author's open source modularization benchmark (`ios-modularization-benchmark`), gives a controlled case: 20 modules (4 core, 16 domains) and 17 test targets, in the **tree** topology only, where each domain is one module importing the domains it uses. Module topology is out of scope here.

- The tree-topology sources are copied into `subjects/civitas/` with a `Package.swift` generated from the Tuist manifest, and built for macOS. One file, `DesignSystem/Sources/MacOSShims.swift`, turns the handful of iOS-only SwiftUI modifiers into no-ops. No benchmark edit touches it.
- `scripts/make-civitas.py` builds a local git repository: a base commit, then one commit per catalogue edit, applied cumulatively so each commit's diff is exactly one edit. Dates and authors are fixed, so the commit hashes are reproducible.
- Edit kinds: private body, internal body, public body, new private declaration, new public declaration, public signature (a defaulted parameter), comment-only, resource, test-only, CI workflow, script and docs. Each source kind is placed in a core module (CoreModels), a domain hub (Identity), a middle domain (Wallet) and a leaf (Home) where the code allows. Body edits rewrite an expression without changing behaviour (operands swapped), so the line holds an operator and seeded bugs can be planted on it.
- The usual harness runs on the resulting history: every selector, the oracle, and two seeded bugs per edit.
- Civitas tests run in milliseconds, so test time saved is not reported for it. It reports share selected, missed seeded bugs, deciding time, and for Bazel the compile actions run.

## Bazel arm

Part A, Bazel as the hash-based selector:

1. **Civitas first.** BUILD files are generated from the same module list (`swift_library` and `swift_test` from `rules_swift`, macOS). Then swift-argument-parser through `rules_swift_package_manager`, recording every hand fix (expected around C targets, resources and plugins).
2. **Selection.** `bazel-diff` hashes every target at base and head. Selected: test targets whose hash changed. Its time to decide is the overhead. `bazel query 'kind(".*_test", rdeps(//..., set(<changed files>)))'` is recorded as the file-to-target baseline.
3. **Rebuild versus rerun (H3).** `scripts/rebuild-study.py` replays the history in one kept worktree. At each commit `bazel test //...` runs with the build event log, which gives the modules that ran a `SwiftCompile` action and the test targets that ran rather than came from cache. `swift build --build-tests -v` then gives the modules SwiftPM recompiled. Bazel caches a test by its built binary, so it reports two numbers: the targets whose inputs changed (target-determinator, before building) and the tests that actually reran (after building, skipped when the linked binary is byte-identical).
4. **Selector.** `tsel/selectors/hash_cache.py` (moved out of `planned.py`) produces the same `selections.jsonl` rows, so `analyze.py` scores it alongside the others.

Part B, Bazel-native subjects: public Swift projects that build with `rules_swift` or `rules_apple`, have real test targets and history, and build on the study Mac.

## Compiler-index cost (H4)

The pilot charged the compiler index a full indexed build of the base revision for every commit, which made it slower than running everything on swift-argument-parser. That overstates its cost where CI builds anyway. Each Civitas and swift-argument-parser revision is therefore also built three ways: plain `swift build --build-tests`, the same with `--enable-index-store`, and the index query alone. The study reports both the stand-alone overhead and the added overhead (indexed minus plain build, plus query).

## Safety oracles

1. **Real failures.** From each subject's public CI history, find commits whose checks failed and a later commit passed. Re-run the failing commit locally with all tests to get the failing targets.
2. **Seeded failures.** For each replayed commit, mutate only the files it changed (Muter on macOS) and record which tests kill each mutant. Add hand-written mutants at protocol defaults, coding keys, GraphQL fields and fixture keys. A selector is unsafe for a mutant when it skips every test that kills it.
3. **Traps.** 30 to 45 small packages in `traps/`, each one Swift trap with one test that must be selected. Third-party selectors run on them as black boxes.

Every failure is re-run twice; a test that passes on re-run is labelled flaky and excluded from misses.

## Edits made by AI coding agents

Agent-written changes may differ in shape from human ones: more files per commit, more cross-module edits, more added declarations, and more generated or reformatted code. Two sources:

1. Public commits and pull requests in the subjects whose metadata marks them as agent-written (bot accounts, agent co-author trailers), compared with human commits in the same repositories over the same period.
2. Agent edits generated on pinned commits from a fixed list of small tasks per subject (fix an issue, add an option, rename an API), with the agent, model, prompt and seed recorded.

For both, report edit shape (files, declarations and targets touched, fallback triggers hit) and each selector's safety and precision, separately from human commits.

## Per-commit record

For each commit and selector: tests selected, missed failures, tests that could not have failed, selection time, end-to-end time, and which fallback rules fired.

## Environment and pinning

Every subject is pinned to an end commit; replay takes the preceding first-parent commits. Toolchain versions are recorded per run. Runs happen on an Apple silicon Mac and in Linux containers; Linux results are reported only for subjects whose tests run on Linux.

## Threats to validity

- Mutants are stand-ins for real faults; the real-failure oracle checks how far they agree.
- Few fail-then-pass commits exist in some subjects; traps cover constructs real history may not reach.
- Tree-sitter grammar gaps (newer Swift syntax) cause parse-error fallbacks; the SwiftParser variant measures this directly.
- Target-level build time is approximated from a full test build; per-target builds are measured on a sample.
- Six subjects cannot represent every codebase; Civitas adds an iOS-style modular app, built for macOS with a one-file shim, and its edits are synthetic.

## Worked example

`fixtures/sample-modular` holds a `Models` module with a `Character` type and a computed `displayName`, two features that import `Models`, and an app module that uses both features. Editing the body of `displayName`:

- The package graph selects all four test targets.
- The Tree-sitter selector selects `ModelsTests`, `CharacterFeatureTests` (spells `displayName`) and `AppCoreTests` (chain rule), and skips `EpisodeFeatureTests`.

Trap `T001` is the harder, safety case: a protocol extension supplies `description`, which string interpolation calls without anyone spelling it. A plain name search misses the failing test; the package graph catches it; the Tree-sitter selector catches it only by following the conformance from `Invoice` to `Formatter`.
