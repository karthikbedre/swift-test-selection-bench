# Final runs on a Mac

The published numbers come from one Apple silicon Mac with a current Xcode. The Linux runs in [`results/pilot-linux-swift6.0.3`](../results/pilot-linux-swift6.0.3) were a pilot: they check that the harness works end to end, but cloud timings vary and they use an older Swift.

Each run builds and tests every commit, so plan for long runs and leave the Mac alone while they go.

## 1. Prepare the Mac

- Plug it in, quit other heavy apps, and keep at least 100 GB free.
- Install the current Xcode from the App Store, open it once, then:

  ```bash
  sudo xcode-select -s /Applications/Xcode.app
  xcodebuild -runFirstLaunch
  swift --version          # note it; the run records it too
  xcodebuild -version
  ```

- Install Python 3.10 or newer (the one that ships with macOS is too old):

  ```bash
  brew install python@3.12
  ```

## 2. Get the harness

```bash
mkdir -p ~/bench && cd ~/bench
git clone https://github.com/karthikbedre/swift-test-selection-bench
cd swift-test-selection-bench
git checkout compiler-index-selector   # only until pull request 2 is merged
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                   # the 3 tests that need the index tool are skipped until step 3
```

## 3. Build the index tool

The indexstore-db branch must match your Swift version.

```bash
v=$(swift --version 2>&1 | sed -n 's/.*Swift version \([0-9]*\.[0-9]*\).*/\1/p' | head -1)
if git ls-remote --exit-code https://github.com/swiftlang/indexstore-db "refs/heads/release/$v" >/dev/null; then
  b=release/$v
else
  b=main
fi
echo "using indexstore-db $b"
INDEXSTORE_DB_BRANCH=$b swift build -c release --package-path tools/index-query
pytest                   # all tests should now pass, none skipped
```

## 4. Trial run (a few minutes)

```bash
scripts/run-subject.sh swift-argument-parser 10
cat results/macos/swift-argument-parser/summary.txt
```

You should see four selectors, ten commits and some seeded bugs. If anything errors, stop and send the last lines of `results/macos/swift-argument-parser/run.log`.

Then delete the trial so the full run starts clean:

```bash
rm -rf results/macos/swift-argument-parser
```

## 5. Full runs

One subject at a time, in this order. The second number is how many commits back from the pinned commit in `subjects/subjects.json`.

```bash
scripts/run-subject.sh swift-argument-parser 300
scripts/run-subject.sh swift-nio 100
scripts/run-subject.sh hummingbird 100
scripts/run-subject.sh swift-syntax 100
scripts/run-subject.sh vapor 100
scripts/run-subject.sh swift-composable-architecture 100
```

Rough times from the Linux pilot (4 cores): about 20 seconds per commit for swift-argument-parser and about 4 minutes per commit for swift-nio, plus the seeded bugs. An M-series Mac mini should be faster. Start with these counts; if time allows, raise a count and re-run the same command, and it continues from where it stopped.

Each run keeps the Mac awake (`caffeinate`). If a run is interrupted, run the same command again: commits already done are skipped.

## 6. What each run records

`results/macos/<subject>/`:

| File | What it holds |
|---|---|
| `machine.json` | Mac model, chip, cores, memory, macOS, Xcode and Swift versions, harness commit |
| `selections.jsonl` | For every commit and seeded bug: what each selector chose, its rules and its deciding time (the compiler index's build time included) |
| `oracle.jsonl` | For every commit and seeded bug: build time, and every test target's result and time, failures re-run twice |
| `summary.txt` | Tests selected, test time, deciding time, fallbacks and bugs missed, per selector |
| `run.log` | Progress log (not committed) |

Scratch space you can delete between subjects: `~/.cache/tsel` and `results/macos/<subject>/oracle-worktree`.

## 7. Send the results back

```bash
git checkout -b results-macos
git add results/macos
git commit -m "Mac runs: <subjects>"
git push -u origin results-macos
```

The results are then scored against the pilot and written up for the article.

## Not covered yet

- iOS simulator runs through `xcodebuild` (the sample app). These steps drive Swift packages with `swift build` and `swift test` on macOS.
- Hash-based caching through Tuist.
