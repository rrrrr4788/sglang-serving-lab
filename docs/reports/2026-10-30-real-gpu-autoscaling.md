# Real GPU replica autoscaling acceptance

Date:2026-10-30 America/Los_Angeles. The operator ran the bounded check; the
assistant reviewed the71-event saved JSONL. Scope: two TP1 replicas within one
existing dual-A6000 K3s VM, automatic1→2→1 and idle GPU process release.

## Environment and control

- Dedicated Ubuntu22.04 single VM,14vCPU/48GB host RAM/512GB storage; two RTX A6000
  GPUs,48GB VRAM each. Control plane and GPU workloads share this one node.
- Fixed K3s v1.36.5+k3s1, NVIDIA device plugin v0.20.1, SGLang0.5.21 digest/model
  revision from worker-autoscale.yaml, Qwen/Qwen3-0.6B; TP1/DP1,one GPU per Pod.
- Official Gateway0.3.2,round-robin,automatic retries disabled. Inference authentication
  passed. In this version /v1/models is public metadata; /generate rejects missing
  and incorrect keys with401. Backends/monitoring remain internal ClusterIP/Pod access.
- Prometheus3.7.3,KEDA2.21.0,single managed HPA,target AverageValue4 for Ready TP1
  running+queued,min1/max2,scale-down stabilization120s. No manual worker scaling.
- Staged cloud initializer completed after a Node-registration race was fixed by
  waiting for Node creation before Ready. RuntimeClass and two allocatable GPUs passed.

## Workload and outcome

| Parameter | Value |
| --- | --- |
| Arrival | Up to8 bounded closed-loop clients inside Gateway Pod |
| Request shape |64 input token IDs,2048 output tokens,temperature0,ignore_eos=true |
| Limits |300s admission window or256requests;90s per-request socket timeout |
| Cache/transport | Existing cache retained; native nonstreaming /generate |
| Client results |256 HTTP200,0failed;524288 generated tokens |
| Load window |266.67s; ended at request-count cap |
| Mean E2E |8.182s for this synthetic workload only |

The test intentionally holds request occupancy above the autoscaling target. It
is not a representative application capacity benchmark; no TTFT/TPOT/p95/p99 or
SLO/goodput result was measured. It does not compare TP1 against TP2 performance.

## Observed transitions

Times below are the local observer clock, sampled rather than exact controller
latency. Remote load_elapsed_s has a different clock origin.

| Observer time | Observation |
| --- | --- |
|0s | One Ready worker,HPA desired1,metric0,FallbackFalse |
|19.31s | HPA desired2;Deployment desired/current2,Ready1 |
|191.39s | Two Ready workers |
|193.45s | Each Pod exposes one GPU; UUIDs differ |
|272.40s | Load completion summary received,256success/0failure |
|279.11s | Sampled metric0;two replicas retained |
|383.12s | HPA desired1;Deployment desired/current/Ready1 |
|393.60s | Only survivor Pod remains;Gateway healthy set matches it;host compute process list contains only its GPU UUID;final PASS |

The observed gap from expansion recommendation to two Ready workers is about172s;
it includes scheduling and engine initialization, whose individual costs were not
separately timed. This demonstrates why expansion cannot absorb an instantaneous
burst by itself. No sampled Fallback=True was observed.

## Serving attribution and counter correction

The original worker's completed-request counter rose2→222. The new worker's first
observed count was already1,and it later reached37. Both workers were sampled with
running4 and increasing completion counts after the new worker joined Gateway.
Conservative observed increments are therefore220 and36. Periodic snapshots support
actual serving on both GPUs; they are not per-request tracing or a precise load split.

The original helper assumed the new worker started at0 and wrote220/37 in its PASS
summary (sum257 despite256 client requests). The pre-existing1's source was not
separately measured. The original log was preserved; the helper now baselines each
new URL at its first sample. Replaying the original event stream through the fix
yielded220/36. No extra workload was needed to establish or correct this evidence.

## Evidence and limitations

Private raw artifact: real-scaling-20261030T194524Z.jsonl,71events,
SHA256 `2396b03e201ecb81722ad137269aababa073a6eb001353a83e41bff022e3a277`.
Private load/observer helpers and physical UUID mappings remain with the lab record;
public deployment configuration is under deploy/k3s. No credentials are included.

This accepts the scoped M4 real-GPU elasticity loop alongside the separate local
telemetry failure/fallback test. Shrink happened after load ended: real in-flight
drain,stream cancellation,hard-crash recovery,public HTTPS and rollout/rollback
remain operational acceptance work. No GPU node provisioning or cross-node HA was
performed. Device-process release is distinct from terminating the paid VM.
The VM was still allocated at the end; final billing/teardown is not claimed.
