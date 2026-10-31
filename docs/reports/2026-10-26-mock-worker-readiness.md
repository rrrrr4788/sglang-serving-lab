# CPU mock worker: build and readiness — 2026-10-26

Source: operator-supplied HTTP responses; no independent runtime check was performed.
The inspected implementation is `services/mock-worker/app.py` with fixed direct
FastAPI/Uvicorn requirements. It is a synthetic CPU worker, not model inference.

| HTTP Date (UTC) | Endpoint | Status | Observed body |
| --- | --- | ---: | --- |
| 16:55:26 | /health/live | 200 | alive=true, worker_id=worker-a |
| 16:55:26 | /health/ready | 503 | phase=starting, inflight=0, ready=false |
| 16:55:53 | /health/ready | 200 | phase=ready, inflight=0, ready=true |

The same host mock process was reported to transition from loading to ready.
BOOT_DELAY_S was instructed as 30 seconds; these samples do not measure an exact
startup duration because they do not include the process start timestamp.

Static review found and then rechecked two fixes: dictionary access in readiness,
and a starting-state guard on the warmup transition so it cannot overwrite drain.
W1–W5 passed the current static review and Python AST parsing scope. Static review
is not a runtime test of admission, cancellation or drain.

Unverified: capacity rejection/drain behavior, authentication, official Gateway
protocol compatibility, dual-replica routing, probe failure/restart and drain lifecycle,
GPU scheduling, TP, autoscaling and production reliability.

See [architecture](../architecture.md) and [platform milestones](../platform-roadmap.md).

## Container build observation

The operator supplied a successful Docker build and subsequent image inspection:

- Tag: `sglang-mock-worker:lab01-v1`.
- Local image ID: `sha256:caaa9555770ba5e25dbf13be633b78d13f9bfdd799afbac08b6d7c3a20ad2bc5`.
- Base image index: `python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530`.
- Reviewed Dockerfile copies the dependency lock, runs as UID/GID 10001 and uses a
  single Uvicorn worker on container port 8080. The lock is present in the repository.

The local image ID is not a published registry manifest digest. This build result
alone proves neither container runtime behavior nor availability inside kind;
Pod evidence is recorded separately below, with no Gateway or model inference claim.

## Single-Pod Kubernetes observation

The operator supplied creation/rollout output followed by a Pod listing:

| Field | Observed value |
| --- | --- |
| Namespace / Deployment | sglang-platform / mock-worker |
| Pod | mock-worker-889ffc8f5-l5b29 |
| Ready / status | 1/1 / Running |
| Restarts / age | 0 / 33 seconds |
| Node | sglang-platform-worker |

Rollout initially reported 0/1 available and then completed successfully. The
Deployment used for that observation had /health/live for startup/liveness and /health/ready for
readiness, with BOOT_DELAY_S=30 and explicit CPU/memory requests/limits.

This establishes the reported single-Pod scheduling/startup/final readiness state.
It does not prove the exact readiness transition timing, liveness failure recovery,
Service traffic, gateway compatibility, request drain, replica elasticity or GPUs.
The next acceptance step is one ClusterIP Service and an in-cluster request.

## Single-replica Service observation

The operator supplied successful creation of ClusterIP Service `mock-worker` in
namespace `sglang-platform`. Its EndpointSlice reported one ready backend.
An HTTP POST from the existing Pod used the full Service DNS name:
`http://mock-worker.sglang-platform.svc.cluster.local/generate`.

Observed result: HTTP 200 with `mock=true`,
`worker_id=mock-worker-889ffc8f5-l5b29`, `request_id=service-check` and `delay_s=0.2`.
The Service selector/port mapping were read from the checked-in configuration.

This establishes one reported in-cluster DNS/Service/HTTP path to the single mock
replica. It does not prove multi-replica distribution, capacity rejection, graceful
drain, Gateway compatibility or automatic scaling. A same-Pod client/server path
also does not establish cross-node traffic. Dual-replica readiness is the next check.

## Manual two-replica observation

The operator supplied a later Pod listing:

| Pod | Ready / status | Restarts | Node |
| --- | --- | ---: | --- |
| mock-worker-889ffc8f5-l5b29 | 1/1 / Running | 0 | sglang-platform-worker |
| mock-worker-889ffc8f5-s48l2 | 1/1 / Running | 0 | sglang-platform-worker2 |

The new Pod was 41 seconds old. Two local CPU replicas are Ready and placed on
separate kind worker containers. No placement policy or physical multi-node/GPU
is implied. EndpointSlice transition output and multi-replica request distribution
were not supplied, so they remain unobserved; no recreation is needed to recover
a missed transient snapshot. This was manual scaling, not metric-driven elasticity.

## v2 artifact observation, rollout pending

The operator supplied a successful `sglang-mock-worker:lab01-v2` build and a
completed kind image-load command targeting the dedicated cluster's nodes.
Local image ID: `sha256:8bc0ee54e2d3710c15774dbf53500e667b046baaaaf912b8e73218de351df8e1`.

Source inspection confirmed the v2 readiness path `/health`, logical model
metadata endpoints, rid/request_id alias handling and rejection of stream=true
before admission. Python AST parsing passed. These are static/source observations,
not HTTP or Gateway compatibility results. The latest inspected Deployment file
still referenced v1; v2 rollout is the next operator action and is not verified.

## v2 rollout observation

The operator supplied a completed rollout followed by these container observations:

| Pod | Image tag | Container ready | Restarts |
| --- | --- | --- | ---: |
| mock-worker-784698d9b-dqbt4 | lab01-v2 | true | 0 |
| mock-worker-784698d9b-nhxpm | lab01-v2 | true | 0 |
| mock-worker-889ffc8f5-l5b29 | lab01-v1 | true | 0 |

Rollout output included an old-replica pending-termination phase before success.
The final listing did not show deletionTimestamp or Pod phase, so old-Pod removal
or termination state is not established by this listing. The new v2 replicas are
ready; this is not proof of uninterrupted requests or graceful drain of the old Pod.
Gateway deployment and v2 protocol/stream-rejection HTTP tests remain pending.

## v2 rollout cleanup follow-up

A later operator Pod listing showed only `mock-worker-784698d9b-dqbt4` and
`mock-worker-784698d9b-nhxpm`, both using lab01-v2, phase Running and no deletion
timestamp. The previously listed v1 Pod was absent. Old-Pod disappearance is now
observed; uninterrupted traffic or drain behavior is still not established.

## Gateway discovery identity preparation

The operator supplied creation of ServiceAccount, Role and RoleBinding
`sglang-gateway` in namespace `sglang-platform`. The source Role grants get/list/watch
on core Pods in that namespace. The supplied impersonated `auth can-i watch pods`
check returned yes. This proves that checked watch permission, not a deployed
Gateway, successful worker discovery or request authentication. The official
Gateway deployment is the next step.

## Official Gateway startup observation

The operator supplied successful creation of Deployment and ClusterIP Service
`sglang-gateway`, followed by a successful rollout. Pod
`sglang-gateway-5b7c9c5b85-rq4wl` was 1/1 Running, restart count 0, age 23 seconds,
IP `10.244.2.4`, on `sglang-platform-worker2`. The inspected manifest pins the
official v0.3.2 image and uses `/readiness` as its readiness probe.

Gateway readiness requires at least one healthy worker in this configuration.
This observation does not establish two registered workers, authentication,
cross-replica request distribution, drain or failure recovery. Those checks remain
pending; no assistant-run cluster operation is implied.

## Gateway discovery, authentication and routing acceptance

The operator supplied `/readiness` HTTP 200 with healthy_workers=2 and
total_workers=2. Authenticated `/workers` listed `http://10.244.1.3:8080` and
`http://10.244.2.3:8080`, both model_id=mock-model and is_healthy=true.
Missing and incorrect credentials on `/generate` each returned 401.

Six sequential authenticated requests, gateway-check-0 through gateway-check-5,
alternated between mock-worker-784698d9b-dqbt4 and
mock-worker-784698d9b-nhxpm, three responses each. The request-ID assertions and
final acceptance assertion passed. This establishes the observed in-cluster
Gateway-to-two-mock-workers path, credential rejection, round-robin distribution
and rid propagation. It does not establish external TLS access, native backend
authentication, streaming, graceful termination, failure recovery or autoscaling.

## Manual drain with an admitted request

The operator ran a direct worker-local HTTP check in Pod
`mock-worker-784698d9b-dqbt4`. With one admitted 15-second mock request,
POST `/admin/drain` returned 200 with phase=draining, inflight=1 and ready=false.
Readiness `/health` returned 503 while `/health/live` returned 200. A new
request returned 503; the already admitted request returned 200 with
request_id=before-drain. Final state was drained with inflight=0; the script passed.

This establishes manual application-level drain behavior for that mock Pod.
Gateway removal timing, Kubernetes preStop/SIGTERM handling and failure recovery
were not tested. No Pod replacement output has been supplied; restoration to two
ready replicas remains pending.

## Restoration follow-up

The operator subsequently confirmed restoration after the drained-Pod replacement
instructions. This is an operator report without a new Pod listing or rollout
transcript; no replacement Pod name or independent observation is asserted.
Kubernetes-integrated graceful termination remains the next unverified step.

## Deployment with preStop and termination grace

The operator supplied a successful mock-worker rollout after adding a container
preStop hook and Pod terminationGracePeriodSeconds=180. New Pods
`mock-worker-6c4dcf9f65-ch99q` and `mock-worker-6c4dcf9f65-jp4g2` both reported
container ready=true, grace=180 and no deletion timestamp. The old Pod
`mock-worker-784698d9b-nhxpm` still appeared with container ready=true, grace=30
and deletionTimestamp=2026-10-27T00:39:42Z. This establishes deletion initiation,
not final disappearance or continued eligibility for new traffic.

The inspected hook calls local drain and polls for drained/inflight=0 with a
120-second deadline and 2-second HTTP timeouts. YAML parsing and embedded Python
AST checks passed before publication. The successful rollout does not establish
hook behavior with an admitted request. That acceptance remains pending.

## Admitted request survives normal Pod deletion

The operator ran the client in the separate Gateway Pod, calling worker
`mock-worker-6c4dcf9f65-ch99q` directly by its current Pod IP. After observing
inflight=1 for a 30-second request, the operator normally deleted that worker Pod.
The client observed phase=draining, inflight=1 and ready=false, then received
HTTP 200 with request_id=pod-termination-check and delay_s=30.0. The acceptance
script printed PASS. The separate deletion/rollout output reported deletion and
then moved from 1/2 available to a successful Deployment rollout.

This establishes observed application drain during normal Kubernetes termination,
completion of that admitted request and replacement availability. It does not
prove an uninterrupted Gateway-routed request stream, SIGKILL/process-crash
survival, manual scale-down routing, GPU behavior or autoscaling.

## Manual scale-down observation, routing check pending

The operator scaled Deployment mock-worker to one replica and supplied a
successful rollout. Pod mock-worker-6c4dcf9f65-jp4g2 was 1/1 Running with
restart count 0; mock-worker-6c4dcf9f65-wvlnr was 1/1 Terminating with restart
count 0. Container readiness in the terminating row does not establish its
eligibility for new traffic. Gateway backend removal and successful routing to
the surviving replica remain to be checked, followed by restoration to two.

## Scale-down routing and two-replica restoration

The operator supplied a passing authenticated Gateway check after manual scale-down.
The script asserted exactly one healthy worker with model_id=mock-model and reported
URL `http://10.244.1.5:8080`. Requests scale-down-0, scale-down-1 and scale-down-2
all returned worker_id=mock-worker-6c4dcf9f65-jp4g2 with matching request IDs.
The script printed PASS. The operator then scaled back to two replicas; rollout
moved from 1/2 available to successfully rolled out. No new Pod identity or
post-restoration Gateway worker listing was supplied.

This completes the observed manual 1-to-2-to-1 lifecycle/routing path and
subsequent Deployment restoration. It does not establish metric-driven scaling
or container process-exit recovery.

## Container restart after controlled process exit

After the instructed SIGTERM to the container main process, the operator supplied
a watch of the same Pod, mock-worker-6c4dcf9f65-jp4g2. It changed from 1/1 Running
with restart count 0 to 0/1 Running, 0/1 Completed, then 0/1 Running with restart
count 1. The final row was 1/1 Running with restart count 1, displaying 34 seconds
since restart. No new Pod identity was created in this observation.

This establishes controlled process-exit recovery through a container restart
and subsequent readiness after warmup. It does not establish SIGKILL/OOM recovery,
node failure recovery or preservation of in-flight requests during a crash.
Post-restart Gateway rediscovery and routing acceptance remain pending.

## Gateway readmission after container restart and local lab closeout

The operator supplied the final passing Gateway check. Assertions confirmed two
healthy mock-model backends and correlated request IDs. Requests recovery-0 and
recovery-2 returned mock-worker-6c4dcf9f65-gc9f4; recovery-1 and recovery-3 returned
mock-worker-6c4dcf9f65-jp4g2. The recovered worker therefore received traffic again.

The scoped local CPU lifecycle lab is accepted: readiness, discovery, authentication,
round-robin routing, manual replica changes, drain, normal Pod termination with an
admitted request, and recovery after controlled SIGTERM process exit. These are
operator-supplied observations, not assistant-run runtime checks. The inference
backend is a CPU mock; the Gateway is the real official component. Hard crashes,
OOM, node HA, zero-failure termination traffic, real GPUs and autoscaling remain
outside this acceptance.
