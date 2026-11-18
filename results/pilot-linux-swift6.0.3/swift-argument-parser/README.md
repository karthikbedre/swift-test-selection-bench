# swift-argument-parser: first run

The 60 first-parent commits ending at `d7b6cebecb27`, plus 31 seeded bugs on the lines those commits changed. Swift 6.0.3 on Linux (x86_64, 4 cores). Seven test targets. Every test target was run alone at every head; failures were re-run twice.

| Selector | Test targets selected (mean share) | Test time | Deciding time | Seeded bugs missed |
|---|---|---|---|---|
| Run everything | 1.00 | 908 s | 0 s | 0 of 17 |
| Package graph | 0.61 | 572 s | 0 s | 0 of 17 |
| Tree-sitter | 0.58 | 547 s | 24 s | 0 of 17 |
| Compiler index | 0.55 | 519 s | 374 s | 0 of 17 |

- **Real failures:** none of the 60 commits had a failing test, so safety here rests on the seeded bugs.
- **Seeded bugs:** 31 built; 17 were caught by at least one test, and every selector selected a test that caught each of them. 14 were caught by no test, so they say nothing about selection.
- **Time:** total test time is small (about 15 s per commit if everything runs), so the compiler index's incremental indexed build (374 s over 60 commits) costs more than its narrower selection saves. Tree-sitter's narrowing beyond the package graph roughly pays for its own deciding time.
- **Where they differ:** the compiler index selected fewer targets than Tree-sitter on 3 commits and never more. Tree-sitter fell back to the package graph on 11 commits (macros, macro-like attributes, top-level code, a property wrapper); the compiler index on 5 (declarations not in the index, a resource change).

Small subject, short history: read these as a check that the harness works end to end, not as the study's answer. The larger subjects (swift-nio, swift-syntax) are where deciding time can pay off.

Reproduce: `python scripts/study.py <clone> d7b6cebecb27 60 <out dir>`, then `python scripts/analyze.py <out dir>`.
