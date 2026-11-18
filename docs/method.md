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

Test targets first, because that is what CI systems run and what every approach can express. For subjects where a few large test targets hold most tests (Vapor, swift-composable-architecture), a second pass selects test files and classes inside a target using the same name rules.

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
2. **Hash-based caching.** Tuist selective testing and Bazel, on subjects that build with them. Target-level, like the package graph.
3. **Package graph.** Owning targets of changed files, then every test target that depends on them directly or indirectly. The graph comes from `swift package dump-package`, or from a Tree-sitter reader of `Package.swift` when no toolchain is present.
4. **Tree-sitter syntax selector.** See the README for the five steps. Escalation rules, which carry most of the research contribution:
   - Members Swift calls without the caller spelling them widen to the owning type: `description`, `debugDescription`, `body`, `hash(into:)`, `==`, `encode(to:)`, `init(from:)`, `CodingKeys`, `rawValue`, `makeIterator`, `callAsFunction`, `id`, `wrappedValue`, result-builder methods and initializers.
   - Stored-property changes widen to the owning type (memberwise init, synthesized `Codable`, `Equatable`, `Hashable`).
   - Protocol requirements and protocol-extension members widen to the protocol and every conforming type, following refinement.
   - Inside the changed target, a declaration that uses a changed name is itself changed, until nothing new is added.
   - Fallback to the package graph for: macro declarations and uses, any attribute that may generate code, custom operators and precedence groups, `@propertyWrapper`, `@resultBuilder`, `@dynamicMemberLookup`, `@dynamicCallable`, `@_exported`, changes under `#if`, top-level code and imports, line-sensitive files (`#line`, `#file`, `#function` and similar) for formatting-only edits, and parse errors that touch the changed declarations.
   - The answer is intersected with the package-graph answer.
   - A variant runs the same rules on SwiftParser, with and without its name lookup, to separate parser mistakes from the limits of syntax alone.
5. **Compiler index.** Build the base revision with indexing on, look up the changed declarations' USRs in IndexStoreDB, map referring files to targets, apply the chain rule. Blind spots to record: compiler-synthesized conformances and code outside the built configuration.

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
- Six subjects cannot represent every codebase; the sample app adds an iOS-style modular app.

## Worked example

`fixtures/sample-modular` holds a `Models` module with a `Character` type and a computed `displayName`, two features that import `Models`, and an app module that uses both features. Editing the body of `displayName`:

- The package graph selects all four test targets.
- The Tree-sitter selector selects `ModelsTests`, `CharacterFeatureTests` (spells `displayName`) and `AppCoreTests` (chain rule), and skips `EpisodeFeatureTests`.

Trap `T001` is the harder, safety case: a protocol extension supplies `description`, which string interpolation calls without anyone spelling it. A plain name search misses the failing test; the package graph catches it; the Tree-sitter selector catches it only by following the conformance from `Invoice` to `Formatter`.
