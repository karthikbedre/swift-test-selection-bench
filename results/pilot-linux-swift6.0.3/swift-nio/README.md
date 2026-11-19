# swift-nio: first run

The 40 first-parent commits ending at `013407bd927d`, plus 15 seeded bugs on the lines those commits changed. Swift 6.0.3 on Linux (x86_64, 4 cores). Sixteen test targets. Every test target was run alone at every head; failures were re-run twice.

| Selector | Test targets selected (mean share) | Test time | Deciding time | Seeded bugs missed |
|---|---|---|---|---|
| Run everything | 1.00 | 6,677 s | 0 s | 0 of 6 |
| Package graph | 0.58 | 4,964 s | 0 s | 0 of 6 |
| Tree-sitter | 0.58 | 4,964 s | 70 s | 0 of 6 |
| Compiler index | 0.58 | 4,964 s | 617 s | 0 of 6 |

- **Real failures:** none of the 40 commits had a failing test. One test target failed once and passed on re-run, and was counted as flaky.
- **Seeded bugs:** 15 built; 6 were caught by at least one test, and every selector selected a test that caught each of them. 9 were caught by no test.
- **No narrowing beyond the package graph.** Tree-sitter and the compiler index selected exactly the package graph's targets on all 40 commits. On 17 commits the change itself selects everything (CI workflows, build settings, scripts and test data that no target owns). Tree-sitter fell back to the graph on 11 commits (C shim targets, `#if` blocks, files its grammar could not parse, top-level code), the compiler index on 8. On the 11 commits where Tree-sitter did decide, every dependent test target spelled a changed name: NIOCore sits under nearly every test, and its common types are used everywhere.
- **Time:** the graph alone saves about a quarter of test time. The finer selectors add deciding time and save nothing more here.
- **Nothing selected, correctly:** 4 commits selected no tests. Two change `_NIOFileSystem`, an older copy of the file system module kept for compatibility; the tests depend on the newer `NIOFS` target, so no test covers the changed code. The other two touch only benchmarks and the performance tester.

Reproduce: `python scripts/study.py <clone> 013407bd927d 40 <out dir>`, then `python scripts/analyze.py <out dir>`.
