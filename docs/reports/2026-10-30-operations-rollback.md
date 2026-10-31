# Real-GPU in-flight drain, alert and configuration rollback

Accepted scoped operator-run evidence on 2026-10-30 (America/Los_Angeles;
raw filename uses UTC 2026-10-31). The operator ran the maintenance helper;
the assistant subsequently parsed its original 20-event JSONL and checked the
completion, notification transitions, changed Pod UID and final assertions.
No additional inference or cluster changes were needed for this review.

## Environment and procedure

One dual-RTX-A6000 VM co-located K3s control plane and GPU workloads. One Ready
TP1/DP1 SGLang 0.5.21 replica served Qwen/Qwen3-0.6B through the authenticated
Gateway and Traefik HTTPS. The existing image/model pins, 180-second termination
grace and maxSurge=0/maxUnavailable=1 strategy were retained. See the
[runbook](../operations.md) and [earlier topology evidence](2026-10-28-real-gpu-topologies.md).

KEDA was temporarily paused at one replica with an experiment ownership marker.
After a 3,500-token bounded external SSE request was observed active, the helper
appended a deliberately invalid CLI option to the live engine template. It then
observed normal termination, bad replacement startup, actual private alert
delivery and one expected external 503 before restoring the captured revision.
This was a **configuration rollout with planned downtime**, not an image upgrade.

## Observed timeline

Times are seconds from the observer's initial event, including command/probe
latency. They are sampled observations, not exact server transition timestamps.

| Observer time | Evidence |
| ---: | --- |
| 1.10 | KEDA pause confirmed at one replica |
| 3.46 | Original worker health 200, running requests 1 |
| 4.60 | Invalid CLI configuration released; image unchanged |
| 6.39 | Original worker health 503 while running remained 1; Gateway had zero healthy workers and readiness 503 |
| 12.70 | Original worker health 503, running 0 |
| 35.33 | Invalid replacement start observed; alert pending |
| 49.02 | Alert firing observed |
| 55.94 | Firing webhook received; original SSE result checked: HTTP200, 3,500 tokens and DONE |
| 56.13 | One external inference request returned expected 503 |
| 57.45 | Rollback to captured revision 1 requested |
| 225.35 | Accepted template restored; Deployment revision now 3 |
| 226.75 | Replacement worker Ready and admitted to Gateway; Pod UID differs from original |
| 236.41 | Resolved notification received |
| 236.86 | External authenticated inference returned HTTP200 and 16 completion tokens |
| 238.37 | KEDA resumed without fallback; final PASS |

The 55.94 event records when the helper checked the completed stream, not its
precise finish time. The first firing and resolved notifications had receiver
sequences 1 and 2 and the expected alert name/namespace. Delivery was internal
Prometheus → Alertmanager → private webhook receiver; no person was messaged.

Rollback correctly restores the old template under a new Deployment revision:
revision 3 matching the accepted revision-1 template is normal. The observed
rollback request-to-template-restoration interval was about 168 seconds; no
startup/download subphase attribution was measured. Overall observation lasted
238.37 seconds. This is neither a latency benchmark nor an outage-duration SLO.

## Acceptance and limits

- The admitted real-engine request survived normal Pod termination after health
  became unready and finished its full bounded stream.
- The invalid replacement failed startup; a real firing notification arrived and
  the expected single-replica outage was externally visible.
- Rollback restored the captured template, a replacement Pod, Gateway serving,
  a resolved notification, external inference and automatic scaling ownership.
- This complements the previously accepted real idle HPA scale-down. In-flight
  completion was tested through rollout's normal Pod termination, not by a
  separate HPA scale-down with active traffic.
- No zero-error rollout, spare-capacity strategy, arbitrary-length drain, engine
  image compatibility, hard crash/OOM, node failure, HA or sustained production
  reliability is claimed. Notification history is a bounded in-memory lab sink.
- After reviewing this result, the operator explicitly reported that the VM was
  destroyed. This closes resource teardown on operator confirmation; the assistant
  did not query the provider, inspect a final invoice or independently verify billing.

## Evidence provenance

Original private artifact (unchanged):
`.private/labs/06-operations/operations-20261031T024606Z.jsonl`, 20 events.

SHA-256: `8ca958e6386a5b426112f8f03c59161e1239b98a6c82af0f9e02041934a9b5c1`.

The local original and user-pasted console output agree on the acceptance events.
Credentials, kubeconfig and private recovery ownership metadata are not published.
