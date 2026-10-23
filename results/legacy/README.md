# Imported historical experiments

Imported on 2026-10-23 from the user's existing WSL lab; **not rerun** during integration.
Terminal progress lines and trailing whitespace were removed; experiment arguments and numeric summaries remain.
[manifest.json](manifest.json) records SHA-256 hashes of original and imported files.
The original logs were left unchanged.

| Case | Successful requests | Generated tokens | Output tok/s | Mean TTFT ms | P95 TTFT ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| [A_128_128](length-sweep/A_128_128.txt) | 100 | 6316 | 975.91 | 69.08 | 415.81 |
| [B_1024_128](length-sweep/B_1024_128.txt) | 100 | 6316 | 774.35 | 66.34 | 161.82 |
| [C_128_512](length-sweep/C_128_512.txt) | 100 | 26540 | 1302.33 | 39.03 | 92.76 |
| [D_1024_512](length-sweep/D_1024_512.txt) | 100 | 26540 | 1047.72 | 61.90 | 189.47 |
| [shared](prefix-cache/shared.txt) | 64 | 3793 | 963.10 | 95.69 | 193.90 |
| [unique](prefix-cache/unique.txt) | 64 | 3911 | 757.71 | 174.12 | 276.81 |

These are single-run observations with incomplete environment provenance. Prefix cases
also differ in actual output token counts. See [methodology](../../docs/benchmarks.md)
before interpreting differences. No historical concurrency sweep results were found.
