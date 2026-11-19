#!/bin/bash
# Build tools/index-query against the indexstore-db branch that matches `swift --version`.
# indexstore-db has used release/6.0 style branches and, from Swift 6.3, release/6.4.2 and
# release/6.4.x style ones, so try the full version, then major.minor.x, then major.minor, then main.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
repo=https://github.com/swiftlang/indexstore-db
full=$(swift --version 2>&1 | sed -n 's/.*Swift version \([0-9][0-9.]*\).*/\1/p' | head -1)
minor=$(echo "$full" | cut -d. -f1-2)

branch=main
for b in "release/$full" "release/$minor.x" "release/$minor"; do
  if git ls-remote --exit-code "$repo" "refs/heads/$b" >/dev/null 2>&1; then
    branch=$b
    break
  fi
done
echo "Swift $full: using indexstore-db $branch"

INDEXSTORE_DB_BRANCH=$branch swift build -c release --package-path "$here/tools/index-query"
echo "$branch" > "$here/tools/index-query/.build/indexstore-db-branch"
