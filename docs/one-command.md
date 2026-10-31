[English](one-command.md) | [简体中文](one-command.zh-CN.md)

# One-command deployment to a new GPU VM

This is the integrated entry for the implemented **single-node,two-GPU** profile.
It deploys the serving architecture,not a load/fault experiment or a node fleet.
The launcher and its resume behavior have offline tests; the complete integrated
command has **not yet been run on a fresh GPU VM**. Earlier stages/capabilities
have separate [historical evidence](presentation.md).

## Requirements

Local: Linux/WSL amd64,Python3.10+,OpenSSH,kubectl and the private SSH key.
Remote: new dedicated full Ubuntu22.04/24.04 amd64 VM,systemd,passwordless sudo,
exactly two full NVIDIA GPUs,working580+ driver,nvidia-container-runtime,curl,UFW,
network/disk/RAM for images and model. A GPU-only notebook/container or one-GPU
machine does not match this profile. This does not install drivers or buy resources.

The script downloads and checksum-verifies pinned Helm3.22.1,KEDA2.21.0 and
Traefik42.1.3 locally,so those manual downloads are no longer prerequisites.
It refuses unknown/mismatched cached binaries instead of overwriting them.
Remote SSH trust must be established with fingerprint verification; it never
disables host-key checking. Host80/443 must be available; DNS/CA/registry/model
downloads must be reachable. No local Docker service or existing lab is restarted.

## Preview without side effects

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP --plan
```

Plan mode creates no files,downloads nothing and never contacts a VM. The real
launch authorizes firewall/K3s/application changes,an external HTTPS entry and
small authenticated smoke requests. It does not run autoscaling load,SSE-cancel
or maintenance fault experiments.

## Launch

Replace NEW_VM_IP with the current VM. On the first SSH connection confirm the
fingerprint against the provider where available,then exit that session and run
the second command locally. The launcher prompts for ACME contact without echo.

```bash
ssh -i ~/.ssh/sglang_lab_ed25519 ubuntu@NEW_VM_IP
python3 scripts/cloud/launch.py --host NEW_VM_IP
```

Default hostname: sglang-IP-WITH-DASHES.sslip.io. No purchased domain is required.
It must resolve exclusively to that IPv4. For an owned A record/noninteractive
private contact input:

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP \
  --hostname inference.example.com --contact-file .private/acme-contact.json
```

The private overlay has structure:
```json
{"certificatesResolvers":{"le":{"acme":{"email":"YOUR_CONTACT_EMAIL"}}}}
```

The contact is sent to the CA on issuance; do not commit its overlay or ACME/TLS
material. An input file is optional; a local hidden prompt is the default.
--user/--key/--ssh-port/--api-port adjust SSH/API access; use --help for details.

## Automatic sequence

1. Render host-specific route/contact to a private0600 directory; download/verify tools.
2. Check driver/GPU prerequisites,configure UFW,install pinned K3s/NVIDIA integration.
3. Open a temporary loopback API tunnel,match cluster identity and claim a dedicated
   project namespace with this run's owner token.
4. Deploy private Secret,TP1 worker,Gateway,Prometheus,Alertmanager/receiver and KEDA.
   An unrelated project/KEDA namespace is never adopted.
5. Pass internal auth/TP1/metric/16-token preflight,then enable the single HPA,min1/max2.
6. Install Traefik,open only80/443 in addition to SSH,and apply the restricted route.
   The API and backends remain private; auth is checked before route exposure.
7. Wait for trusted TLS,run external auth/isolation/16-token checks,and require a
   healthy Gateway,alert rule and scaler. Initial startup alerts are allowed to settle.

On success it prints the HTTPS origin. The key remains in .private/cloud-engine.key,
never stdout. The temporary API tunnel closes; use cloud.py tunnel for later
kubectl checks. The same hostname/entry whitelist and shared Gateway/engine Secret
limitations apply as in [HTTPS](https.md) and [architecture](architecture.md).
Grafana remains the Compose dashboard; this command does not add cloud Grafana/DCGM.

## Resume after failure

A private stage record lives at .private/deployments/VM_IP/state.json.
No automatic teardown occurs; failures preserve resources and remain billable.
Fix the reported prerequisite,last stage,DNS or connectivity,then:

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP --resume
```

Repeat custom hostname/SSH identity options from the original command. Changing
--api-port to a free local port is allowed. Resume validates source/config hashes,
saved HTTPS inputs,cached charts/Helm,cluster UID,namespace UID and ownership.
A previously accepted auth/TLS/serving result is rechecked rather than treated as
proof of current health. A per-host lock prevents concurrent launchers.

Only an incomplete owned application stage may reapply the same pinned manifests.
Completed stages are skipped. The original standalone cloud.py deploy keeps its
refusal to reapply existing workloads. This is not a migration/reconciliation tool:
different code/config,foreign namespace,replaced cluster or a reused IP is rejected.
Do not edit/delete state to force adoption. A partial local render without a
recorded hash may leave an unused private temporary directory for inspection.

## Verification and teardown

```bash
python3 scripts/check_repository.py
python3 -m unittest discover -s tests -v
```

Tests simulate downloads,SSH,Kubernetes,resume and failure paths; no paid host is
used. This is not a claim of cloud end-to-end acceptance for the launcher.
For bounded runtime experiments use [acceptance](acceptance.md) separately.

Expect startup to depend strongly on cold image/model download; the earlier
20–40minute planning estimate is not a measured launcher runtime. Save evidence,
explicitly destroy the VM in the provider and confirm its state afterward.
Closing this script,tunnels or Pods does not stop billing. No resource purchase,
automatic VM deletion,HA guarantee or node scaling is included.
