# Integration verification — 2026-10-23

## Passed

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

## Not performed

- Starting the new three-service deployment or moving the existing server into Compose.
  This avoids port conflicts, competing GPU allocations, and interruption of the lab.
- End-to-end authenticated inference through the new deployment. `scripts/smoke.py`
  is provided to check that after a deliberate cutover.
- Rerunning historical benchmarks, running the new concurrency sweep, verifying fresh
  model download, or proving performance on other hardware.
- A browser visual review of dashboard charts. Provisioning and queries were validated
  through APIs; exact chart appearance has not been visually inspected.

The current standalone server still has its original loopback-only, unauthenticated
configuration. The required API key applies when the new Compose deployment is started.
See [migration.md](migration.md) for a deliberate cutover and rollback procedure.
