#!/usr/bin/env bash
# Run only on the dedicated Ubuntu GPU VM; cloud.py uploads this file and manifests.
set -euo pipefail
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ $EUID == 0 ]] || fail 'Run through sudo.'
base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
version='v1.36.5+k3s1'
installer_sha='46177d4c99440b4c0311b67233823a8e8a2fc09693f6c89af1a7161e152fbfad'
config=/etc/rancher/k3s/config.yaml
marker=/etc/rancher/k3s/sglang-bootstrap
ssh_port=${1:-22}
[[ $ssh_port =~ ^[0-9]+$ ]] && ((ssh_port > 0 && ssh_port < 65536)) || fail 'Invalid SSH port.'
for tool in nvidia-smi nvidia-container-runtime curl ufw systemctl sha256sum cmp; do
  command -v "$tool" >/dev/null || fail "Missing prerequisite: $tool (driver/toolkit are provider prerequisites)."
done
[[ $(uname -m) == x86_64 && -d /run/systemd/system ]] || fail 'Requires amd64 systemd VM.'
. /etc/os-release
[[ $ID == ubuntu && ( $VERSION_ID == 22.04 || $VERSION_ID == 24.04 ) ]] || fail 'Requires Ubuntu 22.04/24.04.'
mapfile -t drivers < <(nvidia-smi --query-gpu=driver_version --format=csv,noheader)
[[ ${#drivers[@]} == 2 ]] || fail 'This profile requires exactly two visible NVIDIA GPUs.'
for driver in "${drivers[@]}"; do
  major=${driver%%.*}
  [[ $major =~ ^[0-9]+$ ]] && ((major >= 580)) || fail 'Pinned CUDA 13 image requires driver 580+.'
done
if [[ -e $marker ]]; then
  [[ $(cat "$marker") == "$version" ]] || fail 'Bootstrap version mismatch; inspect before upgrading.'
  cmp -s "$config" "$base/deploy/k3s/k3s-server.yaml" || fail 'Existing K3s config differs; no overwrite.'
else
  [[ ! -e $config && ! -d /var/lib/rancher/k3s && ! -e /etc/systemd/system/k3s.service ]] || fail 'Existing unmanaged K3s; no overwrite.'
  ! command -v k3s >/dev/null || fail 'Existing unmanaged K3s binary.'
  [[ -z $(nvidia-smi --query-compute-apps=pid --format=csv,noheader) ]] || fail 'GPU already in use.'
  if command -v docker >/dev/null; then
    [[ -z $(docker ps -q) ]] || fail 'Running Docker workloads; dedicated fresh VM required.'
  fi
  ! ufw status | head -n 1 | grep -qx 'Status: active' || fail 'Existing active firewall; inspect instead of replacing policy.'
  ! ufw show added | grep -q '^ufw ' || fail 'Pre-existing firewall rules; inspect instead of adding conflicting rules.'
  ufw default deny incoming
  ufw default allow outgoing
  ufw default deny routed
  ufw allow "$ssh_port/tcp"
  ufw allow from 10.42.0.0/16 to any
  ufw allow from 10.43.0.0/16 to any
  ufw route allow from 10.42.0.0/16
  ufw deny 6443/tcp
  ufw --force enable
  install -d -m 755 /etc/rancher/k3s
  install -m 600 "$base/deploy/k3s/k3s-server.yaml" "$config"
  printf '%s\n' "$version" > "$marker"
fi
if command -v k3s >/dev/null; then
  installed=$(k3s --version | head -n 1)
  [[ $installed == "k3s version $version "* ]] || fail 'Installed K3s version mismatch.'
else
  installer=$(mktemp)
  trap 'rm -f -- "$installer"' EXIT
  curl -fL --retry 2 --connect-timeout 20 --max-time 120 \
    'https://raw.githubusercontent.com/k3s-io/k3s/v1.36.5%2Bk3s1/install.sh' -o "$installer"
  printf '%s  %s\n' "$installer_sha" "$installer" | sha256sum -c -
  env -i PATH="$PATH" INSTALL_K3S_VERSION="$version" sh "$installer" server
fi
systemctl is-active --quiet k3s || fail 'K3s is not active; inspect service rather than restarting blindly.'
k=(k3s kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml --context default)
# K3s may become active before the kubelet has registered its Node object.
"${k[@]}" wait --for=create node/sglang-gpu-01 --timeout=180s
"${k[@]}" wait --for=condition=Ready node/sglang-gpu-01 --timeout=180s
"${k[@]}" get runtimeclass nvidia >/dev/null
"${k[@]}" -n kube-system apply -f "$base/deploy/k3s/nvidia-device-plugin.yaml"
"${k[@]}" -n kube-system rollout status daemonset/nvidia-device-plugin-daemonset --timeout=180s
for ((attempt=0; attempt<60; attempt++)); do
  count=$("${k[@]}" get node sglang-gpu-01 -o 'jsonpath={.status.allocatable.nvidia\.com/gpu}')
  if [[ $count == 2 ]]; then
    printf 'PASS: K3s %s, NVIDIA RuntimeClass, two allocatable GPUs. No model deployed.\n' "$version"
    exit 0
  fi
  sleep 2
done
fail 'Two allocatable GPUs not observed within 120 seconds.'
