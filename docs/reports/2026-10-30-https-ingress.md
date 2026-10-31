# External HTTPS inference acceptance

Date:2026-10-30 America/Los_Angeles. The operator ran the full external acceptance
helper from local WSL, outside Kubernetes, and supplied the successful stdout.
It is transcribed privately as external-check-output.txt, SHA256 `7416ecb940750f0df201283773d206fc61fd953d4734cfc455d3a6d31a58e8fb`.
This records a bounded native inference check, not a general production-readiness
or all-networks security audit.

## Implemented route

External client → Traefik HTTPS → internal SGLang Gateway Service → private TP1
SGLang worker. The same single-node dual-A6000 K3s environment used in the
[autoscaling report](2026-10-30-real-gpu-autoscaling.md) remains in use.

- Official Traefik Chart42.1.3,app v3.7.16,image digest pinned in
  [values](../../deploy/k3s/traefik-values.yaml). Helm release sglang-edge revision1
  deployed; actual Deployment name is sglang-edge-traefik.
- One nonroot Pod,host80/443,persistent local-path ACME storage. acme.json metadata
  was checked as mode0600,UID/GID65532; no key material or contact email was read
  into the report. Restart/renewal behavior has not yet been tested.
- A temporary IP-encoded sslip.io hostname resolved to the VM. No domain was bought;
  it is not an owned permanent service name. A different VM IP requires a route update.
- Let's Encrypt HTTP-01 via port80; native inference only on HTTPS443. Certificate
  registration contact is supplied through an ignored private Helm overlay.
- [IngressRoute](../../deploy/k3s/inference-ingress.yaml) allows only this Host,
  POST,and exact /generate,/v1/chat/completions,/v1/completions paths. Existing
  Gateway Bearer-key validation protects those endpoints. The actual valid request
  below exercised /generate; the other two API shapes were not exercised.
- Configured ingress guards:16 active requests,rate8/s and burst16 with default
  source-IP criterion. They are not tuned quotas; rejection behavior was not tested
  in this acceptance run.

## Operator-run external results

| Check | Observed result |
| --- | --- |
| Default trust-store and hostname verification | TLS1.3 succeeded;no -k or disabled validation |
| Certificate notAfter | Jan29 01:05:01 2027 GMT |
| Missing credential POST /generate |401 |
| Incorrect credential POST /generate |401 |
| Correct credential native generation |200;16 completion tokens |
| HTTPS GET /workers,/metrics,/engine_metrics |404 |
| HTTPS GET /get_server_info,/server_info,/v1/models |404 |
| HTTPS GET /dashboard/,/api/rawdata |404 |
| HTTPS POST /metrics and /v1/models with empty body |404 asserted by the full helper |
| HTTP POST /generate without credential |404 |
| Direct TCP30000,8080,9090,6443 |Unreachable from this external client |

The helper never sends a credential over HTTP and refuses redirects instead of
forwarding Bearer headers. Backend/direct-port failures are reachability evidence
from one client and time, not proof of NetworkPolicy or every network's behavior.
The assistant independently checked trusted TLS,unauthenticated generate401,
metrics/workers404 and plaintext generate404 before the operator's full run; it did
not run the authenticated generation on the operator's behalf.

## Remaining acceptance

This passes the HTTPS entry sub-item of M5. Streaming and cancellation/resource
reclamation,real in-flight drain,actionable alert,controlled update/rollback,and
final cloud teardown remain pending. No HA,independent frontend/backend credential
isolation or multi-tenant authorization is claimed. The private ACME volume/Helm
release must not be exported with credentials. The VM remains allocated and billed;
certificate issuance does not terminate paid compute.
