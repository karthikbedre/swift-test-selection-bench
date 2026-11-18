# Subjects

Pinned in `subjects/subjects.json` (heads of the default branch on 2026-11-17). Target counts are from each `Package.swift` at that pin.

| Subject | Test targets | Targets | Runs on | Why it is here |
|---|---|---|---|---|
| [swift-nio](https://github.com/apple/swift-nio) | 16 | ~60 | Linux, macOS | Deep graph with one central module (NIOCore), the case where target-level selection reruns nearly everything |
| [swift-syntax](https://github.com/swiftlang/swift-syntax) | 17 | ~50 | Linux, macOS | Layered modules, no external dependencies, large generated sources |
| [swift-argument-parser](https://github.com/apple/swift-argument-parser) | 7 | ~21 | Linux, macOS | Small and fast; property wrappers and snapshot fixtures exercise fallbacks and resource rules |
| [Hummingbird](https://github.com/hummingbird-project/hummingbird) | 4 | ~13 | Linux, macOS | Mid-size framework with a chain of feature modules |
| [Vapor](https://github.com/vapor/vapor) | 3 | ~8 | Linux, macOS | Few large test targets: where selection finer than targets should pay off |
| [swift-composable-architecture](https://github.com/pointfreeco/swift-composable-architecture) | 2 | ~4 | macOS | Macro-heavy iOS library: measures how often syntax must fall back |
| Sample iOS app (to be published) | — | — | macOS | Swift packages with GraphQL, fixtures and Tuist, for the GraphQL, fixture and hash-caching cases |

Alternates: swift-openapi-generator (generated code, reference tests) and sourcekit-lsp (13 test targets, but its manifest needs the toolchain loader and its tests are slow).

## Early observation from a selection-only trial (no tests run)

On the last 60 commits of swift-argument-parser and swift-nio, most commits where the Tree-sitter selector ran fewer test targets than the package graph were documentation-comment edits. On swift-nio, about one source file in five has a Tree-sitter parse error somewhere (empty tuple expressions, `sending`, compound `#if` conditions), so the parse-error fallback fires often. This supports running the same rules on SwiftParser as a separate arm.
