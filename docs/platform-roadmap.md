[English](platform-roadmap.md) | [简体中文](platform-roadmap.zh-CN.md)

# Platform roadmap

| Milestone | Scoped status |
| --- | --- |
|M0 Single GPU|Authenticated Compose,monitoring,bounded scheduling/client accepted|
|M1 Local bootstrap|Separate three-node CPU kind,namespace/quota,version pins accepted|
|M2 Lifecycle/routing|Mock discovery,routing,normal drain,controlled restart/rejoining accepted;not hard crash/node HA|
|M3 Real topology|Single-node TP2 and two TP1 replicas,physical devices,auth and attributed routing accepted;not speedup|
|M4 Replica scaling|Mock and real1→2→1;local telemetry failure/recovery;real256 HTTP200,distinct GPUs,idle release accepted|
|M5 External operations|HTTPS,stream/cancel,real in-flight normal termination,private alerts,failed-config rollback accepted with downtime;VM destruction operator-confirmed|
|M6 Engineering delivery|Public parameterized tools, integrated launch/resume, bilingual guides and offline regression checks delivered; integrated launcher remains offline-validated only|

Goal: a quick-deploy serving showcase with replica autoscaling inside an existing
GPU pool, with reproducible engineering evidence. No customer business or production SLA is invented.
The original full VM co-located control plane and GPUs; split-node networking,
GPU node purchase/join,control-plane HA,PD/EP,multi-node TP/PP and fleet scheduling
are separate future work. A full benchmark matrix is not a v1 release gate.

Gaps remain explicit:rate-rejection,full application-log redaction,certificate
renewal/restart,public OpenAI request shapes,cloud Grafana/DCGM and sustained
capacity/SLO claims. Do not turn a selected design or offline test into runtime proof.
Fresh clones use public source; private keys/kubeconfig/evidence stay ignored.

Release checks cover repository/tests, architecture consistency and secret boundaries.
An additional paid-VM rerun is not a v1 release requirement; retain the explicit
offline-only status of the integrated launcher. Historical real-GPU observations
remain valid within their original scope even though generalized tooling has not
been rerun. See [evidence](presentation.md) and [language policy](documentation.md).
