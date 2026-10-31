# Local mock load-driven autoscaling verification

Observed2026-10-28 America/Los_Angeles; saved run file has UTC timestamp
20261029T013216Z. Evidence is operator-run output and its locally parsed private
JSONL record. The assistant did not run the inference load.

## Setup

Dedicated CPU-only kind-sglang-platform, Kubernetes1.36.1; project namespace
sglang-platform. The original Compose stack and other clusters were preserved.

- [Mock Deployment](../../deploy/kind/mock-worker.yaml): lab03-v1, per-worker
  capacity2, default synthetic request duration10seconds, startup warmup30seconds,
  existing180-second termination grace/preStop drain. No GPU requests.
- Mock /metrics exports current inflight and readiness gauges from the same
  locked state used for admission and drain.
- [Prometheus](../../deploy/kind/prometheus.yaml): digest-pinned3.7.3,5-second
  per-Pod scraping. Both targets were observed with up1/ready1/inflight0.
- KEDA Chart/App2.21.0, project-local Helm3.22.1, bounded component
  [values](../../deploy/kind/keda-values.yaml). Three components Ready and
  external.metrics API Available; one initial operator restart was observed.
- [ScaledObject](../../deploy/kind/mock-worker-scaledobject.yaml) creates the
  sole mock-worker-hpa. AverageValue target1, min1/max2, scale-down
  stabilization120seconds. The query sums ready-worker inflight with checks for
  up/metric coverage; ignoreNullValues=false. Fallback is configured at failure
  threshold3/static replicas2; it was exercised in the separate outage test below,
  not during this load run.

## Controlled load and observations

The test started with desired/current/ready all1, valid average metric0 and no
fallback. Two bounded closed-loop clients sent requests through the authenticated
Gateway for120seconds. Each successful response had mock=true, the expected
request ID and delay_s10. HTTP waiting timeout was20seconds; the observer window
was capped at360seconds. The test never manually scaled the worker or changed
the scaling rule.

Controller times below are first-observed samples relative to the local observer
start, not exact event timestamps. Remote load events use their own elapsed clock.

| First observed seconds | HPA desired | Deployment desired/current/ready | Observation |
| --- | --- | --- | --- |
| 0.5 | 1 | 1/1/1 | Idle baseline, metric0, fallbackFalse |
| 11.1 | 2 | 2/2/1 | Higher demand caused desired2 while new replica was not ready |
| 47.1 | 2 | 2/2/2 | Both replicas ready; Gateway had also observed two healthy workers |
| 129.3 | 2 | 2/2/2 | Load ended and sampled metric reached0; replicas initially held |
| 237.1 | 1 | 1/1/1 | Controller reduced desired count and Deployment returned to one |
| 237.4 | 1 | 1/1/1 | Gateway healthy backend URLs matched the remaining Ready Pod; PASS |

All24 requests returned HTTP200; failures0. The existing worker completed17
and the new worker completed7. Unequal totals are expected because the new
worker entered service after startup; this is not a balanced steady-state sample.
Both workers actually returned successful requests. Sampled controller records
kept fallbackFalse throughout, distinguishing load-driven scaling from fallback.
A sampled metric of1500m means1.5 in request-average units, not CPU millicores;
it is a sampled aggregate, not a synchronized count of concurrent requests.

The stabilization window operates on recent scaling recommendations, not an
exact countdown starting at the first observed metric0. PollingInterval15 is
configured, but with min1 and no metric caching, HPA's own synchronization drives
1-to-N scaling; the KEDA warning about that setting was informational.

## Gateway registry and test correction

The first attempt failed before sending load because the test incorrectly
required healthy_workers==total_workers==1. Read-only reproduction showed one
healthy current Pod and one old unhealthy registration. In Gateway0.3.2 total
counts all registrations. The revised test requires the healthy URL list to match
current non-deleting Ready Pod URLs exactly and rejects extra/wrong/duplicate
healthy URLs. The corrected preflight passed twice before the operator reran.

The successful run ended with healthy1/registered2; the old unhealthy entry was
still present. Registry cleanup itself was not fixed or claimed. This is an
observability/management limitation, tracked separately from healthy routing.

## Scope

This proves the scoped local CPU mock load-driven1-to-2-to-1 control loop,
including readiness delay, actual new-worker requests and healthy routing after
scale-down. It does not prove GPU autoscaling, cloud node provisioning, production
capacity or failure recovery. Scale-down happened after the load completed;
in-flight drain is covered by earlier local lifecycle evidence, not re-proven here.
The local Prometheus-unavailable/fallback test subsequently passed as documented
below. Real-GPU elasticity remains pending.

## Separate Prometheus-unavailable/fallback check

The operator ran a second bounded check, saved under UTC timestamp
20261029T014158Z (still2026-10-28 America/Los_Angeles). It sent no inference
load. Only the experimental lab-prometheus Deployment in this dedicated kind
namespace was temporarily scaled to0; original Compose monitoring was preserved.
A finally block restored its initial replica count1.

| First observed seconds | Observation |
| --- | --- |
| 0.4 | Prometheus1Ready, worker1Ready, failures0/fallbackFalse |
| 0.8 | Experimental Prometheus desired0/ready0 |
| 16.2 | Metric failures2; worker remained1 |
| 31.6 | Metric failures4/fallbackTrue |
| 47.0 | Worker desired2/current2/ready1 |
| 82.9 | Worker2Ready while Prometheus remained0; fallback accepted |
| 83.0 | Prometheus restoration requested |
| 88.3 | Prometheus1Ready; metric recovery had not yet completed |
| 108.8 | Metric failures0/fallbackFalse; worker still2 |
| 211.4 | Prometheus1Ready, worker desired/current/ready1; PASS |

These are sampled observations, not promises about exact controller timing or
failure-threshold cadence. ScaledObject Ready remainedTrue while the source was
unavailable; that flag alone is not evidence of metric-source health. Failure
counts and Fallback state showed the source failure and recovery.

This demonstrates local fail-safe replica selection under complete loss of the
experimental Prometheus endpoint, followed by recovery and delayed scale-down.
The query did not convert this outage into a zero-load signal. It does not prove
detection of all partial service-discovery losses. Prometheus used emptyDir, so
its prior short-term monitoring history was lost when the Pod was deleted;
independently saved JSONL observations and this report were retained.

The scoped local Lab03 control loop and telemetry-failure check are accepted.
Cloud GPU elasticity, representative serving capacity and public deployment
remain separate milestones. No commit or push was performed as part of recording
these results.
