# index-query

A small command line tool on [IndexStoreDB](https://github.com/swiftlang/indexstore-db) that the compiler-index selector calls. Given an index store and a list of changed declarations, it prints every file whose code refers to them.

## Build

The indexstore-db branch must match `swift --version`. `scripts/build-index-query.sh` tries `release/<full version>` (such as `release/6.4.2`), then `release/<major.minor>.x`, then `release/<major.minor>` (such as `release/6.0`, the older naming), then `main`, and builds with the first that exists. To pick one by hand:

```bash
INDEXSTORE_DB_BRANCH=release/6.4.2 swift build -c release --package-path tools/index-query
```

Or let the script choose:

```bash
scripts/build-index-query.sh
```

The selector finds the binary at `tools/index-query/.build/release/index-query`, or at `$TSEL_INDEX_QUERY`. It finds `libIndexStore` next to the toolchain's `swift`, or at `$TSEL_LIBINDEXSTORE`.

With a distribution-packaged toolchain (such as Ubuntu's `swiftlang`), clang may not find the libdispatch and blocks headers. Pass them in:

```bash
I=$(dirname $(dirname $(readlink -f $(which swift))))/lib/swift
swift build -c release --package-path tools/index-query -Xcc -I$I -Xcc -I$I/Block -Xcxx -I$I -Xcxx -I$I/Block
```

## Protocol

One JSON request on stdin, one JSON response on stdout.

```json
{
  "store": "/path/.build/debug/index/store",
  "database": "/tmp/scratch-db",
  "library": "/path/usr/lib/libIndexStore.so",
  "changes": [{"path": "/abs/Sources/Models/Character.swift", "startLine": 11, "endLine": 13, "mode": "range"}],
  "addedNames": ["initials"],
  "maxDepth": 50
}
```

- `range`: every definition whose name sits on a line in `[startLine, endLine]`.
- `nearest`: the last definition at or above `startLine`, for ranges the selector could not map to a declaration.
- `addedNames`: declarations that exist only at head. Existing symbols with the same base name are treated as changed, because a new overload can win resolution at an existing call site.

The response lists `files` (path to module), the changes it resolved and those it could not, and how many symbols it seeded and visited. Inside the changed module, references are followed to the declarations that contain them until nothing new turns up, so a change to an internal helper reaches the public API that uses it. Protocol requirements and the declarations that satisfy or override them are followed both ways.

## What it cannot see

Calls the compiler makes without a recorded reference, such as `description` reached through string interpolation (trap T001), code the compiler synthesizes (`Codable`, `Equatable`, `Hashable`, memberwise initializers), and code under `#if` branches the build did not take. The selector records these as blind spots rather than patching them, because measuring them is part of the study.
