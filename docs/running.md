# Running the study

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

## Still to build on the Mac

- `tools/index-query`: a small Swift command line tool on IndexStoreDB that, given an index store and a list of changed declarations, prints the files that reference them. The compiler-index selector calls it.
- Mutation runs with Muter on the files each commit changed.
- Linux containers: `swift:<version>` images for the Linux-capable subjects.

Large result files stay out of git; publish summaries and CSVs.
