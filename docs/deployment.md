[English](deployment.md) | [简体中文](deployment.zh-CN.md)

# Deployment and operation

Run in Ubuntu/WSL2 with Docker Compose2.30+,NVIDIA GPU/driver and working Docker GPU
support for Compose. Inventory existing GPU/port ownership first. Initial image/model
downloads need network and disk; no fixed VRAM guarantee is made.
CPU kind is a separate simulation and does not run the real LLM.

## Compose baseline

```bash
git clone https://github.com/rrrrr4788/sglang-serving-lab.git
cd sglang-serving-lab
cp .env.example .env
# Edit .env and set separate, private random values for both required secrets.
# Generate each with: python3 -c 'import secrets; print(secrets.token_hex(32))'
chmod 600 .env
# Use hex secrets; the examples below load this private file as trusted shell input.
set -a; . ./.env; set +a
python3 scripts/validate.py
docker compose up -d --wait --wait-timeout 300
docker compose ps
python3 scripts/smoke.py
```

Use separate random private SGLANG_API_KEY and GRAFANA_ADMIN_PASSWORD values. Smoke rejects missing/wrong credentials and sends one small generation after loading. Ports are loopback30000/9090/3001. Grafana provisions SGLang Lab → SGLang Serving Overview,stable datasource UID prometheus. Dashboard edits belong in versioned JSON; idle quantiles may be absent. Memory panels are SGLang allocations,not DCGM device utilization.

## Create a separate CPU kind cluster

```bash
mkdir -p .private
kind create cluster \
  --name sglang-platform \
  --config deploy/kind/cluster.yaml \
  --image kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5 \
  --kubeconfig .private/kubeconfig \
  --wait 180s
```

This pinned kind0.32.0/Kubernetes1.36.1 topology is three containers sharing one host,not independent machines or GPUs. kubeconfig stays ignored and separate; do not disturb another cluster. Use kubectl1.36.1. Cloud tooling uses Helm3.22.1; no conflicting Helm4 requirement applies.

## Verify node readiness

```bash
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform \
  wait --for=condition=Ready node --all --timeout=60s
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform get nodes -o wide
```

## Namespace and quota

```bash
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform \
  -n sglang-platform apply -f deploy/kind/namespace.yaml
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform \
  -n sglang-platform describe resourcequota local-budget
```

## Configuration and operation

Required secrets: SGLANG_API_KEY and GRAFANA_ADMIN_PASSWORD; GRAFANA_ADMIN_USER
defaults admin,MODEL_PATH defaults Qwen/Qwen3-0.6B. Internal0.0.0.0 serves the Compose
network; public host bindings remain127.0.0.1. The pinned engine exempts health/
metrics from auth,so keep them private. Compose alone has no TLS,multi-tenant
isolation,ingress rate limiting or HA. Docker admins can inspect env values.

Stop this Compose project with docker compose stop; restart with docker compose
up -d --wait --wait-timeout 300. Named volumes retain caches/
monitoring. Volume removal is separate/destructive. Updating the Grafana password
env does not reset an existing database. After edits run scripts/validate.py;
runtime smoke needs an authorized running service and private exported key.

The CPU quota limits workload requests/limits,not kind containers/system services.
Mock/Gateway lifecycle results are in the [presentation](presentation.md).
After retaining evidence,kind delete cluster --name sglang-platform deletes only
that named experiment; this teardown was not performed in the reported local run.

## Cloud profiles

Follow [cloud initialization](cloud-rebuild.md),[HTTPS](https.md) and
[acceptance](acceptance.md). Require NVIDIA RuntimeClass/device plugin,two allocatable
GPUs,local-path storage and private sglang-engine-auth Secret. TP2,dualTP1 and
autoscale manifests all target sglang-worker: select one explicitly. Stop traffic
and terminate the old profile before switching. Autoscale omits replicas for HPA.
Do not apply the whole directory. Single-node results do not prove TP performance,
independent frontend/backend credentials or node/storage HA.
