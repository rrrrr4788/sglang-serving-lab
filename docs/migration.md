# Existing deployment and migration

## Observed on 2026-10-23

The WSL repository `~/sglang-serving-lab` was clean at `706df5d` and matched GitHub.
The existing deployment is separate from that repository:

| Component | Existing owner | Local port |
| --- | --- | --- |
| `sglang-server` | Standalone Docker container | 30000 |
| `sglang-prometheus` | `~/sglang-production/compose.yaml` | 9090 |
| `sglang-grafana` | `~/sglang-production/compose.yaml` | 3001 |

All three ports were loopback-bound. The existing server command did not include
`--api-key`. This integration did not change that running container. Prometheus's
existing target was `host.docker.internal:30000` and was healthy. No saved user
dashboards were found in the existing Grafana database snapshot; the versioned
12-panel dashboard is newly authored against observed metrics.

The new project is named `sglang-lab`, avoids fixed container names, and uses
`sglang:30000` for scraping. Its volumes differ from the `sglang-production` volumes.
It does not automatically import the old Prometheus database or Grafana accounts.

## Deliberate cutover

1. Review and merge/pull the repository changes. Keep the current deployment running
   while reviewing files; do not run the new stack against occupied ports/GPU.
2. Save the old launch command and configuration privately. Back up monitoring volumes
   with an appropriate consistent backup procedure if their history must be retained.
   Export any dashboards created since the snapshot through Grafana's UI; never commit
   its database or user-account exports.
3. Prepare `.env` with distinct random credentials. Run `python3 scripts/validate.py`.
   Have the exact old container/configuration available for rollback.
4. Schedule a brief local maintenance window. Stop the existing components explicitly:

   ```bash
   docker stop sglang-server
   docker compose -f ~/sglang-production/compose.yaml stop
   ```

5. In this repository, start `docker compose up -d`. Follow logs and run the documented
   authentication smoke check. Confirm Prometheus target `sglang:30000` is up and the
   provisioned Grafana dashboard appears. Model download/startup may take time; the old
   standalone container did not mount a persistent model cache, so a fresh download
   may be necessary.
6. Keep the old stopped containers and volumes until the new stack is accepted.
   To roll back, stop this project first, then use `docker start sglang-server` and
   `docker compose -f ~/sglang-production/compose.yaml start`.
   Rollback restores the previous loopback-only server without API-key protection.

For parallel testing, change all three host ports and check available GPU capacity
first. Changing ports alone does not reserve extra GPU memory. Never attach the old
container to a public network or remove authentication to make the new setup work.

This document describes a future cutover; these stop/start actions were not executed
as part of the repository integration.
