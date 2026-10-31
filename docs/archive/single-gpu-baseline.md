# Single-GPU baseline: integration and verification record

Scope: historical integration on 2026-10-23 and follow-up work through 2026-10-24.
This consolidates the old migration, initial verification and retrospective pages.
Their original text is retained in local private history; original committed versions
remain in Git history. Current instructions are in [deployment](../deployment.md),
not the old one-time cutover procedure.

## Resulting baseline

| Capability | Evidence and limit |
| --- | --- |
| Reproducible deployment | Compose pins the observed SGLang 0.5.21 image digest, persists cache and provisions monitoring |
| Authentication/inference | After cutover, missing/wrong keys were rejected; authenticated model listing/inference succeeded |
| Monitoring | Prometheus targets and Grafana data confirmed; idle quantiles do not establish latency performance |
| Bounded overload | One 32-request run: 24 HTTP 200, 8 queue-full HTTP 503, then successful smoke check |
| Queue timeout | Five seconds configured and observed in recreated container; actual timeout triggering untested |
| Client behavior | Six non-streaming simulations and one real short inference; no exactly-once/server cancellation guarantee |
| Historical performance | Six logs and import hashes; incomplete provenance prevents strong causal claims |

## Initial checks before cutover

The source repository was inspected at `706df5d`. The old model container was separate
from the new Compose project and loopback-bound without an API key. Integration
identified its SGLang version/digest and preserved it while checking new artifacts.

Initial checks covered Python syntax, JSON, imported SHA-256 hashes, resolved Compose
ports, disposable Prometheus configuration validation, all twelve dashboard expressions
against the existing metrics API, and disposable Grafana provisioning. Authentication
logic was checked at function level in the pinned image; that was not end-to-end
verification of the future Compose deployment.

At that point the new stack had not started, historical benchmarks were not rerun,
and dashboard appearance was not inspected in a browser. These initial limits must
not be confused with later authenticated deployment checks.

## Subsequent cutover

The old standalone/monitoring arrangement was later replaced by the repository's
`sglang-lab` Compose project. Authentication and real inference checks passed;
monitoring was confirmed. The old migration instructions concerned that historical
cutover, including rollback to an unauthenticated loopback-only server; they are
not the current deployment or security recommendation.

## Known limits

- Single host/GPU and static shared key; no user-level permissions, TLS ingress,
  replica/node elasticity, failover or production SLA was established.
- Running/queue limits 8/16 and timeout 5 seconds are initial protective settings,
  not optimal capacity. Queue-full rejection does not prove timeout behavior.
- Restart/health configuration exists, but crash/hang recovery was not tested.
  Client cancellation does not prove GPU work was cancelled.
- Historical logs do not establish strict prefix-cache/CUDA Graph improvements.
- No multi-GPU, Kubernetes lifecycle, streaming recovery or node HA evidence is
  implied by these baseline checks.

## Detailed evidence

- [Overload check and parameters](../overload-protection.md)
- [Client policy and verification scope](../reliable-client.md)
- [Benchmark methodology and limits](../benchmarks.md)
- [Imported logs and provenance](../../results/legacy/README.md)
- [Current architecture and target platform](../architecture.md)
