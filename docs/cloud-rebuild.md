[English](cloud-rebuild.md) | [简体中文](cloud-rebuild.zh-CN.md)

# Rebuild the single-node GPU environment

For the integrated route, start with [one-command deployment](one-command.md). This page retains the lower-level stages; do not combine the two flows on an existing deployment.

Use WSL/Linux,Python3.10+,OpenSSH,kubectl and a **new dedicated full VM**.
Requires Ubuntu22.04/24.04 amd64,systemd,passwordless sudo,exactly two full NVIDIA
GPUs,working driver major580+,nvidia-container-runtime,curl,UFW and sufficient
disk/RAM/download access. GPU containers/notebooks alone do not satisfy this path.
The script does not install drivers,upgrade the OS,buy resources or destroy VMs.

## Prepare before renting

Helm3.22.1 and KEDA2.21.0 are pinned. Execute downloads/checks individually; stop
on any checksum failure and extract only after success. Private tool downloads are
runtime artifacts, not missing private source dependencies.

```bash
mkdir -p .private/bin .private/vendor
curl -fL https://get.helm.sh/helm-v3.22.1-linux-amd64.tar.gz \
  -o .private/vendor/helm-v3.22.1-linux-amd64.tar.gz
printf '%s  %s\n' 896cf63684a42a723d61c980369d6e588330927deb13676ca0d85006dd6da0ea \
  .private/vendor/helm-v3.22.1-linux-amd64.tar.gz | sha256sum -c -
tar -xOf .private/vendor/helm-v3.22.1-linux-amd64.tar.gz linux-amd64/helm > .private/bin/helm
chmod 700 .private/bin/helm
curl -fL https://kedacore.github.io/charts/keda-2.21.0.tgz \
  -o .private/vendor/keda-2.21.0.tgz
printf '%s  %s\n' a7da56bf41a33dad9d2fc82a6fdecee552fff947d80bf1e1dbcf4db0f9e26dee \
  .private/vendor/keda-2.21.0.tgz | sha256sum -c -
```

Set the newly allocated address. Establish SSH trust first and verify the host
fingerprint through the provider when available; host-key checks are never disabled.

```bash
export GPU_HOST='NEW_VM_IP'
ssh -i ~/.ssh/sglang_lab_ed25519 "ubuntu@$GPU_HOST" true
python3 scripts/cloud/cloud.py host --host "$GPU_HOST"
python3 scripts/cloud/cloud.py deploy --host "$GPU_HOST"
```

Host stage inventories prerequisites,allows the actual SSH port before UFW
activation,allows Pod10.42/16 and Service10.43/16 networking,denies public6443,
installs checksum-verified K3s v1.36.5+k3s1 and waits for Node creation then Ready.
NVIDIA device-plugin v0.20.1 advertises exactly two allocatable GPUs.
An ownership marker permits safe rechecking without reinstall/restart.
Existing unrelated K3s/workloads/firewall policies cause refusal.
--user/--key/--ssh-port/--api-port override SSH/API defaults.

Deploy owns a temporary127.0.0.1 tunnel and compares kube-system UID via SSH and
that tunnel before backing up/replacing private kubeconfig at0600. It refuses an
occupied local port,existing project Deployments or an already-owned external
metrics API. No global context is changed. The engine key is privately generated
or reused and sent as a Secret without printing it.

It creates namespace/PVC/Secret,operations ConfigMaps/Alertmanager/receiver,
one TP1 worker,Gateway/RBAC,Prometheus and KEDA. It waits for readiness and external
metrics API availability. It **does not apply the ScaledObject**,publish HTTPS or
start inference/load. Initial readiness must be checked separately.
Never apply the entire deploy/k3s directory: worker profiles target the same
Deployment and are mutually exclusive.

## Continue from a separate terminal

The temporary deploy tunnel closes at completion/error. Keep this foreground
tunnel running for subsequent checks:

```bash
python3 scripts/cloud/cloud.py tunnel --host "$GPU_HOST"
```

In the working terminal:

```bash
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --run-inference
```

Then follow [acceptance](acceptance.md) for scaler activation and bounded load,
[HTTPS](https.md) for the external entry and [operations](operations.md) for recovery.
Profiles: worker-tp2.yaml is one Pod/two GPUs with replica scaling disabled;
worker-replicas.yaml is two one-GPU TP1 replicas; worker-autoscale.yaml omits
replicas for HPA ownership. Stop traffic and terminate the previous profile before
switching on a two-GPU host. These use local-path RWO model cache,not storage HA.

## Failures, timing and teardown

Failed stages preserve resources. There is no automatic retry,profile switch or
uninstall. Inspect partial initialization before rerunning deploy. Do not share
kubeconfig,Secrets,raw Pod arguments or startup logs containing credentials.

Budget roughly20–40minutes to first Ready model,mainly cold downloads; this is an
estimate,not measured script time. Save local evidence,then explicitly destroy the
VM and verify provider state. Closing tunnels/scaling to zero does not stop billing.

Earlier operator-run host/deploy and later runtime experiments passed; see
[presentation/evidence](presentation.md). The operations extension was installed
separately afterward. Current parameterized tools and expanded integrated bootstrap
were checked offline,not rerun end-to-end on a fresh GPU VM. Original VMs were
reported destroyed; do not reuse their addresses.
