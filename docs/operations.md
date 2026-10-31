[English](operations.md) | [简体中文](operations.zh-CN.md)

# Alert, drain and configuration rollback

One real-GPU experiment passed; see the [report](reports/2026-10-30-operations-rollback.md).
The later public tool passed offline recovery replays, not a fresh GPU rerun.

## Install and inspect

New cloud initialization includes operations. Existing deployments must create
rule ConfigMaps before Prometheus mounts them. Keep the tunnel open; GPU_HOST
is the current VM:

```bash
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -k deploy/k3s/operations
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-alertmanager --timeout=180s
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-alert-receiver --timeout=180s
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -f deploy/k3s/prometheus.yaml
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-prometheus --timeout=180s
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --snapshot-only
```

Prometheus replacement resets emptyDir history, not saved local evidence.
Baseline: Gateway200/one healthy URL,rule inactive/ok,Alertmanager200,KEDA Ready/no fallback.
Empty receiver history is normal before first delivery.

SGLangNoReadyWorker evaluates every5s and fires after15s without a scrape-confirmed
Ready worker. Missing telemetry is unhealthy **for this alert**, not zero scaler
load. Discovery/scrape failures also trigger it: inspect Pods,rollout,events and
metrics before attributing the cause. Prometheus→Alertmanager→private ClusterIP
receiver delivers firing/resolved with5s initial group wait. The sink stores selected
fields/128 events in memory and loses history on restart. No email/chat delivery,
durable incident management or NetworkPolicy isolation is claimed.

## Planned interruption

Require [HTTPS](https.md),one Ready TP1 worker,healthy alert baseline and an active
ScaledObject; no other traffic/concurrent operators. maxSurge0/maxUnavailable1
**temporarily removes all serving capacity**. New requests receive503 during recovery.

```bash
python3 scripts/acceptance/operations.py --host "$GPU_HOST" \
  --base-url "$INFERENCE_URL" --run-maintenance
```

The helper saves the accepted revision/template and recovery metadata; marks/pauses
KEDA at1; admits a3500-token stream; releases an invalid CLI option without changing
image; requires old health503/running1 followed by full completion, bad replacement
startup, actual firing delivery and external503. It restores the captured revision,
checks replacement UID/Gateway/resolved/16-token inference and removes its own pause.
The existing180s grace uses SGLang0.5.21 normal SIGTERM drain.

This tests bounded normal termination/configuration failure with planned downtime,
not an image upgrade,hard crash,HA or zero-error rollout. Idle HPA shrink is separate;
this experiment did not directly trigger HPA scale-down with active traffic.

## Recovery and release

.private/evidence contains recovery-<UTC>.json and operations-<UTC>.jsonl.
Possible mutation is recorded before sending it; lost acknowledgements still enter
cleanup. Foreign ownership/template changes stop automatic overwrite.
After interruption inspect the record and ownership before retrying.
Use the **captured original revision** for confirmed experiment-owned changes:

```bash
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout undo deployment/sglang-worker --to-revision=CAPTURED_REVISION
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-worker --timeout=1200s
```

Confirm Ready Pod/Gateway and inference before removing this run's annotations:
autoscaling.keda.sh/paused-replicas and sglang.lab/ops-run. Do not clear another
operator's pause. Recovery failure keeps scaling paused; incomplete evidence
remains FAIL even if cleanup succeeds.

The historical238.37s observation is not an SLO. Rule syntax,offline replay and
actual firing/resolved delivery passed; standalone amtool was not run.
The operator confirmed VM destruction; final billing was not independently checked.
Stopping tunnels/Pods does not stop billing: save evidence,explicitly destroy the
VM at the provider and confirm its state.
