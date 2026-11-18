# Trap packages

Each trap is a small Swift package with one Swift construct that hides a dependency from the text, one edit, and one test that must be selected after that edit. `trap.json` in each folder records the edit, the tests that must run and the tests a precise selector may skip.

| Id | Construct | Status |
|---|---|---|
| T001 | Protocol-extension default for a requirement called implicitly (`description` via string interpolation) | Done. Package graph and Tree-sitter select the failing test; the compiler index skips it (Swift 6.0.3, Linux) |
| T002 | Synthesized `Codable` and a renamed `CodingKeys` case | Done. Tree-sitter selects the failing test; the compiler index and the interface-only variant skip it (Swift 6.4.2, macOS) |
| T003 | Synthesized `Equatable`/`Hashable` after adding a stored property used in a `Set` | Done. Every selector selects the failing test (Swift 6.4.2, macOS) |
| T004 | New overload that wins resolution at an existing call site in another module | Done. Every selector selects the failing test (Swift 6.4.2, macOS) |
| T005 | New protocol-extension member that shadows a default the conformer relied on | Planned |
| T006 | Property wrapper `wrappedValue` change | Planned |
| T007 | Result builder method change seen through a SwiftUI-style DSL | Planned |
| T008 | Attached macro that adds members (`@Observable`-style) | Planned |
| T009 | Freestanding macro expansion change | Planned |
| T010 | Custom operator implementation change | Planned |
| T011 | `#if` branch active only in the test configuration | Planned |
| T012 | `@_exported import` re-exporting a changed module | Planned |
| T013 | Default argument value change | Done. Every selector selects the failing test (Swift 6.4.2, macOS) |
| T014 | Enum case added; exhaustive `switch` in a dependent | Planned |
| T015 | Fixture file key read by a test through `Bundle.module` | Planned |
| T016 | GraphQL operation field change with generated Swift types | Planned |
| T017 | `#line`/`#file`-sensitive assertion after a formatting-only edit | Planned |
| T018 | `@dynamicMemberLookup` key path change | Planned |
| T019 | Associated type default change | Planned |
| T020 | Typealias retarget across modules | Planned |

`scripts/run-traps.py <out dir>` checks every trap (tests pass before the edit; the `must_select` tests fail after it and the `may_skip` ones still pass) and scores every selector on it.

The list grows to 30 to 45 as the study runs. Every trap must build and its test must pass before the edit and fail after it, on macOS and, where possible, Linux.
