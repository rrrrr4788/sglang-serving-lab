[English](README.md) | [简体中文](README.zh-CN.md)

# SGLang Serving Lab

A quick-deploy SGLang inference reference platform with GPU replica autoscaling.
A new dedicated two-GPU VM can be configured through one deployment entry; the
serving architecture supports authenticated routing, monitoring and bounded recovery.
The single-GPU Compose baseline remains available. This is an engineering
showcase, not a production SLA or an automatic GPU-node provisioning service.

## Demonstrated capabilities

- Pinned SGLang0.5.21/Qwen3-0.6B,authentication,Prometheus/Grafana,bounded queue/client.
- Single-node dual-A6000 K3s: one TP2 replica,then two TP1 replicas with attributed routing.
- Real1→2→1 elasticity,256 HTTP200,distinct GPUs,new replica serving,idle process release.
- Trusted HTTPS,credential rejection and private management routes/ports.
- Complete128-token SSE and cancellation with abort signal/sustained idle.
- 3500-token in-flight completion,failed-configuration alert,rollback,resolved,inference
  and KEDA recovery,with planned downtime.

See [bilingual presentation/evidence](docs/presentation.md) and
[implemented architecture](docs/architecture.md). Original VMs were reported
destroyed; no live demo endpoint is promised. Public parameterized tools were
checked offline,not rerun on a fresh GPU VM.

Client → Traefik → official Gateway → workers. Prometheus feeds KEDA's single HPA
and Alertmanager's private receiver. Accepted cloud sessions co-located control
plane and GPUs on one VM. They do not prove node purchasing,HA,uninterrupted updates,
capacity/SLO gains,multi-node TP or tenant isolation.

## Start the local single-GPU baseline

Requires Ubuntu/WSL2,Docker Compose2.30+,compatible NVIDIA GPU/driver and Docker GPU
support. Check resource/port ownership and [deployment](docs/deployment.md) first.

```bash
git clone https://github.com/rrrrr4788/sglang-serving-lab.git
cd sglang-serving-lab
cp .env.example .env
# Set distinct private SGLANG_API_KEY and GRAFANA_ADMIN_PASSWORD values in .env.
# Generate each with: python3 -c 'import secrets; print(secrets.token_hex(32))'
chmod 600 .env
set -a; . ./.env; set +a
python3 scripts/validate.py
docker compose up -d --wait --wait-timeout 300
python3 scripts/smoke.py
```

Ports bind only to127.0.0.1: inference30000,Prometheus9090,Grafana3001.
Grafana provisions SGLang Lab → SGLang Serving Overview. Credentials/caches remain private.
Cloud initialization can take much longer than this local quick start.

## One-command cloud deployment

After SSH trust is established, deploy the pinned single-node/two-GPU stack with one entry. It prompts for ACME contact, verifies small requests and enables min1/max2 replica scaling. --resume continues only the same owned environment. The integrated launcher is offline-tested, not fresh-GPU validated.

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP
```

[Requirements, preview and resume](docs/one-command.md).

## Reproduce the cloud path

[Initialize a new dedicated two-GPU VM](docs/cloud-rebuild.md) →
[Preflight and bounded scaling](docs/acceptance.md) →
[HTTPS](docs/https.md) → [Streaming and recovery](docs/operations.md).
Save evidence and explicitly destroy the VM at the provider afterward.
These stages are operator-run; no node purchasing or automatic VM teardown.
Never apply the entire deploy/k3s directory.

## Offline verification

```bash
python3 scripts/check_repository.py
python3 -m unittest discover -s tests -v
python3 scripts/cloud/cloud.py --help
python3 scripts/acceptance/operations.py --help
```

These checks cover public-only CLI,explicit target/DNS guards,SSE framing,private
render behavior and recovery replays. They do not rerun cloud serving.

## Files and documentation

deploy/kind and services/mock-worker contain CPU simulation; deploy/k3s contains
pinned cloud profiles/routing/scaling/edge/alerting. scripts/cloud initializes hosts
and renders HTTPS; scripts/acceptance holds public bounded tools/payloads.
monitoring holds Compose dashboards; tests contains offline checks; docs/reports
contains historical evidence.

[Documentation](docs/README.md) · [Roadmap](docs/platform-roadmap.md) ·
[Language policy](docs/documentation.md).
Presentation/operating guides have English and Simplified Chinese counterparts;
historical reports retain their source language with a bilingual evidence summary.
API keys,kubeconfig,ACME material and personal notes stay out of Git.
