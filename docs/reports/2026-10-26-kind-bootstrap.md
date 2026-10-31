# CPU kind bootstrap

Recorded 2026-10-26. Status: local bootstrap accepted; three CPU nodes Ready and namespace/quota created.
Source: supplied operator terminal output, without an embedded execution timestamp.
Both initial and follow-up observations below come from supplied operator output;
no independent runtime check was performed for this report.

## Configuration and observation

- Dedicated cluster `sglang-platform`; explicit context `kind-sglang-platform`
  and private kubeconfig were used for the reported node command.
- `deploy/kind/cluster.yaml` specifies one control-plane and two CPU worker
  containers, with Kubernetes API bound to loopback.
- All three nodes reported Kubernetes v1.36.1 and containerd 2.3.1.

| Node | Observed condition | Age |
| --- | --- | --- |
| sglang-platform-control-plane | Ready | 28 seconds |
| sglang-platform-worker | Ready | 16 seconds |
| sglang-platform-worker2 | NotReady | 16 seconds |

The three node containers reported approximately 903 MiB combined memory use in
that snapshot. Their displayed 29.22 GiB limit is not a reservation or separate
physical memory allocation per node. Existing Compose services, the older kind
control-plane and unrelated containers were also running; this is not a fresh
endpoint-health or performance check of those services.

## Follow-up readiness observation

The operator ran an explicit wait with the dedicated kubeconfig/context. It returned
`condition met` for all three nodes. The following `get nodes` showed all three
Ready at age 22 minutes, version v1.36.1.

Node readiness acceptance has passed. The initial worker2 condition is no longer
present in that follow-up snapshot; its earlier cause was not diagnosed and no
remediation is claimed. Namespace/resource quota creation is recorded separately below.

## Namespace/resource quota observation

A later supplied apply/describe result confirmed creation of namespace
`sglang-platform` and ResourceQuota `local-budget` from `deploy/kind/namespace.yaml`.

| Resource | Used | Hard |
| --- | ---: | ---: |
| limits.cpu | 0 | 4 |
| limits.memory | 0 | 4Gi |
| pods | 0 | 12 |
| requests.cpu | 0 | 2 |
| requests.memory | 0 | 2Gi |

Zero reported usage is consistent with no business Pods deployed in this namespace.
The namespace/quota objects exist; rejecting an over-quota workload was not tested.
This quota covers resource declarations in the namespace, not system/node overhead.

## Unverified

No model/mock workload, official Gateway, over-quota rejection check,
real GPU scheduling, TP inference, autoscaling, HTTPS, recovery or teardown is
established by these node/container snapshots.

See [bootstrap instructions](../deployment.md#cpu-kind-bootstrap) and
[platform milestones](../platform-roadmap.md).
