# Real two-GPU topology and routing verification

Observed on 2026-10-28. Evidence is operator-supplied terminal output plus the
saved four-request check output, parsed locally without running further inference.
This report records a short rented GPU session, not a production deployment claim.

## Environment and configuration

- One Massed Compute dedicated VM through Spheron: Ubuntu22.04.5, 14vCPU,
  approximately94GiB visible RAM, 512G root disk. The VM runs both K3s control
  plane and GPU workloads; no separate CPU control node was used this session.
- Two NVIDIA RTX A6000 GPUs, 49140MiB each, driver580.126.09. GPU interconnect
  reported PHB (PCIe host bridge); no NVLink was shown.
- K3s v1.36.5+k3s1 / containerd2.3.4-k3s1.36. Node Ready; RuntimeClass nvidia.
  NVIDIA device plugin v0.20.1 with runtimeClassName:nvidia rolled out; node
  capacity=2 and allocatable=2.
- Engine SGLang0.5.21, pinned image digest and model revision in
  [TP2](../../deploy/k3s/worker-tp2.yaml) and
  [replicas](../../deploy/k3s/worker-replicas.yaml). Model Qwen/Qwen3-0.6B,
  revision c1899de289a04d12100db370d81485cdf75e47ca, served as qwen3-lab.
- Official Gateway0.3.2, digest pinned in
  [Gateway configuration](../../deploy/k3s/gateway.yaml), round_robin policy,
  namespace-scoped Pod discovery, retries disabled. Gateway and engine share
  the configured Secret key; independent frontend/backend credentials were
  not implemented in this profile.
- Model cache PVC Bound:20Gi/RWO/local-path. This is node-local storage; the
  request size does not enforce a host filesystem capacity quota.
- Host UFW allows SSH and cluster-internal Pod/Service communication. Cluster
  management uses an SSH loopback tunnel and private kubeconfig. Gateway is
  ClusterIP; no public inference ingress or model port was configured.

The worker profiles describe the same Deployment and must be applied separately.
The old TP2 Deployment was scaled to zero and its Pod deletion observed before
applying the two-replica profile. This was an interrupting profile switch.

## TP2: one engine using two GPUs

Deployment rollout succeeded; one Pod was Ready with zero restarts. Distinct
physical GPUs ran sglang::scheduler_TP0 and sglang::scheduler_TP1, each using
about30494MiB. Runtime metadata reported tp_size2/dp_size1/version0.5.21.
Memory usage includes runtime caches/allocations and is not a model-weight size.

Missing and incorrect inference credentials returned401. Correct credentials
returned200 from /generate, with16completion_tokens and text beginning Paris.
The Gateway subsequently reported one healthy backend; missing/wrong credentials
were rejected and generation through its Service succeeded with16tokens.

## TP1 replicas: two engines using one GPU each

After the profile switch, both Pods were Ready with zero restarts. Each reported
tp_size1/dp_size1 and saw exactly one physical GPU. The GPUs were distinct:

| Pod suffix | GPU UUID suffix | Runtime |
| --- | --- | --- |
| rk62r | 30bb45c744cc | TP1 / DP1 |
| zngdc | 506a6217f153 | TP1 / DP1 |

Gateway readiness reported healthy_workers2/total_workers2. Initial generation
requests succeeded; request-count attribution below verifies traffic reached both.

## Four-request routing and latency check

All inference requests went through the Gateway Service from a worker Pod.
Direct backend access was used only to snapshot metrics. Other inference test
traffic was stopped. Four sequential requests (concurrency1) used the same64
input token IDs, temperature0, ignore_eos=true and32output tokens. Each request
had a120-second total deadline and a10-second network-read timeout. Existing
prefix cache state was retained; this was not a cold-cache benchmark.

| Request | HTTP | Input/output tokens | Client TTFT ms | Client TPOT estimate ms | Client end-to-end ms |
| --- | --- | --- | --- | --- | --- |
| 0 | 200 | 64/32 | 170.457 | 2.931 | 261.447 |
| 1 | 200 | 64/32 | 161.591 | 2.990 | 254.447 |
| 2 | 200 | 64/32 | 73.076 | 3.229 | 173.289 |
| 3 | 200 | 64/32 | 71.437 | 3.017 | 165.095 |

- Success4/4, failed0. Backend completed-request counters each increased by2,
  for a total of4; the check's routing assertion passed. This proves both replicas
  processed inference during this controlled window, without identifying each
  individual response's backend.
- Mean client TTFT119.140ms; mean TPOT estimate3.042ms;
  mean client end-to-end213.570ms.
- Window elapsed0.855s; aggregate output-token rate149.771tokens/s, computed from
  full-precision timing as128output tokens divided by elapsed wall time.
- TTFT is time to the first token-bearing SSE event. TPOT estimate is time between
  first/last token-bearing events divided by the number of tokens after the first
  event. These observations include Gateway, networking and stream batching;
  they are not pure GPU execution times. Timing excludes the user's public
  network/SSH path because the client ran inside the cluster.

The counter is sglang:num_requests_total. In the pinned release, business-request
completion increments it; generated health checks disable request metrics.
Sources: [collector](https://github.com/sgl-project/sglang/blob/v0.5.21/python/sglang/srt/observability/metrics_collector.py),
[health handler](https://github.com/sgl-project/sglang/blob/v0.5.21/python/sglang/srt/entrypoints/http_server.py).

## Verification limits and remaining work

Both real GPU topologies and basic authenticated routing were observed. This
four-request sequential check does not measure representative production capacity,
p95/p99, SLO/goodput, cache speedup or TP performance improvement. The lower later
TTFTs do not isolate a cause; cache and warmup state were not controlled.

TP2 and TP1 were not compared under an identical timed benchmark. Same-node
replicas do not provide node HA. Real autoscaling, drain/in-flight recovery,
public TLS, cancellation, rollout/rollback and actionable alerts remain unverified.
The short stream check does not satisfy the broader streaming/cancellation milestone.

Bootstrap manifests were exported to
[NVIDIA device plugin](../../deploy/k3s/nvidia-device-plugin.yaml) and
[K3s server configuration](../../deploy/k3s/k3s-server.yaml); their YAML, runtime
selection and non-secret configuration fields were checked locally.
The K3s installation version is recorded above and is separate from the server
configuration file. The operator subsequently supplied a provider screenshot
showing this VM TERMINATED, with Running0/Reserved0/Terminated1. The page
reported1.32hours runtime and USD1.49 total usage at the displayed
USD1.13/hour rate. This confirms release of the experimental VM; it is not
a final invoice or an account-wide storage/snapshot audit. No additional volume
was created in the recorded procedure. Evidence and bootstrap configuration
remain in the local project; no further use of the destroyed cluster is planned.
