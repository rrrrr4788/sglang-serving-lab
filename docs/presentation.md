[English](presentation.md) | [简体中文](presentation.zh-CN.md)

# Project presentation and evidence

## Outcome

The primary showcase is quick deployment with replica autoscaling inside an existing GPU pool.

Deploy authenticated SGLang,choose TP2 versus independent TP1 replicas,route via
the official Gateway,scale within a two-GPU pool,publish restricted HTTPS and
recover from one bounded failed configuration. Real-GPU evidence came from
single-node dual-RTX-A6000 VMs,not a GPU fleet.

| Local date | Observation | Source and limits |
| --- | --- | --- |
|2026-10-28|TP2 then two TP1 replicas,four requests attributed2+2|[Topology](reports/2026-10-28-real-gpu-topologies.md),not TP speedup|
|2026-10-28|Mock scaling24 successes;telemetry failure→fallback2→recovery1|[Mock](reports/2026-10-28-mock-autoscaling.md),CPU control only|
|2026-10-30|Real1→2→1,256 HTTP200,distinct GPUs,new worker serving,idle GPU process release|[Scaling](reports/2026-10-30-real-gpu-autoscaling.md),8 closed-loop/64 input/2048 output;not capacity/SLO proof|
|2026-10-30|Trusted TLS1.3,missing/wrong key401,private paths404/ports unreachable,16-token inference|[HTTPS](reports/2026-10-30-https-ingress.md),one client;rate rejection untested|
|2026-10-30|Full128-token SSE,early close,abort1,sustained idle|[Streaming](reports/2026-10-30-stream-cancellation.md),active slot reclaimed,not VRAM pool|
|2026-10-30|3500-token in-flight completion,failed-config alert,rollback,resolved,16-token recovery,KEDA resumed|[Operations](reports/2026-10-30-operations-rollback.md),238.37s observation,planned503 window;not HA|
|After sessions|Operator confirmed VM destruction|First provider screenshot1.32h/USD1.49;second final bill not independently checked|

Raw JSONL remains private; reports record hashes. Dates use America/Los_Angeles,
while some filenames use the following UTC day. Original private helpers produced
these records. Later public parameterized tools have offline checks only,not
fresh-GPU acceptance.

## Engineering decisions

- TP jointly computes a model; replicas route separate requests. Kubernetes
  whole-device placement differs from SGLang token scheduling.
- Replica creation is not readiness. Cold model startup has a real operational cost.
- Missing telemetry is not zero load; local fallback evidence is distinct from
  the real load-driven elasticity result.
- With no spare serving capacity,single-replica failure causes downtime. Recovery
  exercises ownership,drain,notification and rollback.
- Cancellation clears active work; preallocated KV/cache may remain reserved.

## Limits and reproduction

No automatic GPU node purchase/join,cross-node HA,sustained SLO,cost optimum,
TP-speedup proof or multi-tenant isolation. Rate rejection,full application-log
redaction,certificate renewal/restart,cloud Grafana/DCGM and public OpenAI request
shapes remain untested/outside scope. No running public endpoint is promised.

[Architecture](architecture.md) → [Cloud](cloud-rebuild.md) →
[Acceptance](acceptance.md) → [HTTPS](https.md) → [Operations](operations.md).
Historical reports remain source records; both presentation languages retain the
same facts and limitations.
