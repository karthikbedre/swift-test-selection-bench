# Running the study

For the final runs on a Mac, follow [mac-mini.md](mac-mini.md) step by step.

## Selection only (any machine)

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
mkdir -p ../subjects && cd ../subjects
git clone https://github.com/apple/swift-nio   # and the other subjects in subjects/subjects.json
cd -
tsel replay ../subjects/swift-nio --end b440f7bae8894b5ec42e0f1842fcd77483ab3984 --count 300 \
  --out results/swift-nio/selections.jsonl
```

## Test runs (Apple silicon Mac, and Linux containers for Linux-capable subjects)

1. Install Xcode and note `swift --version`; record it in `subjects/subjects.json`.
2. For each replayed commit, run the oracle once:

   ```bash
   for c in $(jq -r .head results/swift-nio/selections.jsonl); do
     tsel oracle ../subjects/swift-nio "$c" --out results/swift-nio/oracle.jsonl
   done
   ```

   With `swift` on `PATH`, the oracle reads the package graph from `swift package dump-package`.
3. Score:

   ```bash
   tsel score results/swift-nio/selections.jsonl results/swift-nio/oracle.jsonl --csv results/swift-nio/scores.csv
   ```

## Compiler-index selector

Needs a Swift toolchain on `PATH` (macOS with Xcode, or Linux) and `tools/index-query` built once; see [tools/index-query/README.md](../tools/index-query/README.md).

```bash
INDEXSTORE_DB_BRANCH=release/6.0 swift build -c release --package-path tools/index-query
tsel select ../subjects/swift-nio HEAD~1 HEAD --selector package-graph --selector compiler-index
```

The selector checks out the base revision in a scratch worktree (under `~/.cache/tsel`, or `$TSEL_CACHE`) and builds it with `swift build --build-tests --enable-index-store`. That build time is recorded as the selector's overhead. One worktree is kept per subject and moved to each base in turn, so during a replay each build is incremental from the previous commit. Delete the cache between subjects to save disk.

## Still to do

- Mutation runs with Muter (macOS) on the files each commit changed.
- Hash-based caching through Tuist on the sample app.

Large result files stay out of git; publish summaries and CSVs.
