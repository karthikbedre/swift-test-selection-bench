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
scripts/build-index-query.sh
tsel select ../subjects/swift-nio HEAD~1 HEAD --selector package-graph --selector compiler-index
```

The selector checks out the base revision in a scratch worktree (under `~/.cache/tsel`, or `$TSEL_CACHE`) and builds it with `swift build --build-tests --enable-index-store`. That build time is recorded as the selector's overhead. One worktree is kept per subject and moved to each base in turn, so during a replay each build is incremental from the previous commit. Delete the cache between subjects to save disk.

## Civitas

```bash
scripts/make-civitas.py ../subjects/civitas      # builds the local repository with one commit per catalogue edit
scripts/run-subject.sh civitas                   # same harness as the public subjects
```

## Bazel arm

Needs `bazelisk` (`brew install bazelisk`) and the target-determinator binary for your platform from https://github.com/bazel-contrib/target-determinator/releases (v0.34.0 used here), saved as `~/.cache/tsel/bin/target-determinator` or named by `$TSEL_TARGET_DETERMINATOR`. The Bazel version is pinned by each subject's `.bazelversion`. The study runs the `hash-cache` selector on any subject with a `MODULE.bazel` at its end commit.

```bash
tsel select ../subjects/civitas HEAD~1 HEAD --selector hash-cache
scripts/rebuild-study.py ../subjects/civitas <end commit> 28 results/macos/civitas-rebuild   # rebuild versus rerun per edit
```

## Traps

```bash
scripts/run-traps.py results/macos/traps            # every trap: checks it, then scores every selector on it
scripts/run-traps.py results/macos/traps T002 T003  # some traps only
```

## Report

```bash
scripts/report.py results/macos > results/macos/REPORT.md
```

One Markdown file: per-subject summary, why the graph ran everything (H5), the compiler index's cost (H4), the Civitas edit catalogue with the rebuild study (H1 to H3, H7, H8) and traps (H9).

## After a harness fix

Selection never needs the tests, so a fixed selector or manifest reader can be rerun over a finished run without repeating the oracle:

```bash
scripts/reselect.py ../subjects/swift-argument-parser results/macos/swift-argument-parser
```

The previous file is kept as `selections.jsonl.bak`.

## Still to do

- Mutation runs with Muter (macOS) on the files each commit changed.
- Hash-based caching through Tuist on the sample app.
- iOS simulator runs through `xcodebuild`, for Civitas as an iOS app.

Large result files stay out of git; publish summaries and CSVs.
