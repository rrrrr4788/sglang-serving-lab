# Initial integration verification — 2026-10-23

This is a historical snapshot of the initial repository integration, before the
new Compose deployment was started. Statements below describe that point in time,
not the current deployment. This snapshot is retained to preserve the original evidence.

## Subsequent progress

The deployment was later switched to the new Compose stack. Authentication and
inference checks passed; the user confirmed Prometheus targets and Grafana data.
Queue-full rejection and recovery, and the bounded-retry client, were checked later.
These later checks do not retroactively change what was tested during initial integration.

- [Learning plan and current status](learning-plan.md)
- [Overload protection evidence and limits](overload-protection.md)
- [Reliable client implementation and verification scope](reliable-client.md)
- [Project outcome and retrospective](project-retrospective.md)

## Passed during initial integration

- Cloned GitHub main at `706df5d`; original WSL repository was clean and matched it.
- Confirmed the running server reports SGLang 0.5.21 and resolved its immutable image
  digest to the digest now in Compose. No image pull or model download was needed.
- Resolved the new Compose configuration with disposable validation credentials.
  All three published ports bind to loopback. Empty example credentials fail closed.
- Checked Python syntax, JSON parsing, and SHA-256 integrity of the imported evidence.
- Ran Prometheus 3.7.3 `promtool check config` against the new scrape configuration
  in a disposable container with no network.
- Queried all twelve dashboard expressions against the existing Prometheus HTTP API:
  each parsed successfully and returned a series. Idle histogram values can be NaN.
- Started a disposable Grafana 12.2.1 container with no network or published ports,
  mounted the new provisioning files, and verified via its local API that the dashboard
  and datasource UID loaded. Removed the temporary container and its anonymous volumes.
- Tested the authentication decision function in the pinned running image: missing
  and wrong keys are rejected, the correct key is accepted, and metrics are exempt.
  This is a function-level check, not an end-to-end test of the new deployment.
- Original SGLang, Prometheus, and Grafana container IDs and start times remained
  unchanged; all three were still running after validation.

## Not performed during initial integration

- Starting the new three-service deployment or moving the existing server into Compose.
  This avoided port conflicts, competing GPU allocations, and interruption of the lab.
- End-to-end authenticated inference through the new deployment. `scripts/smoke.py`
  is provided to check that after a deliberate cutover.
- Rerunning historical benchmarks, running the new concurrency sweep, verifying fresh
  model download, or proving performance on other hardware.
- A browser visual review of dashboard charts. Provisioning and queries were validated
  through APIs; exact chart appearance has not been visually inspected.

At the time of this initial integration, the standalone server still had its original
loopback-only, unauthenticated configuration. The API key requirement was configured
for the future Compose deployment; authenticated inference was verified after cutover.
See [migration.md](migration.md) for the cutover and rollback procedure.
