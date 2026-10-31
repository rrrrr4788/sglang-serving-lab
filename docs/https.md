[English](https.md) | [简体中文](https.zh-CN.md)

# Reproduce the HTTPS entry

Use a current dedicated VM initialized by [cloud-rebuild](cloud-rebuild.md).
Keep its API tunnel running. Run from repository root in WSL/Linux with Python3.10+,
Bash, curl, kubectl, SSH, verified Helm prerequisites and a private engine key.

Choose CURRENT_HOSTNAME as an owned A record or sglang-IP-WITH-DASHES.sslip.io.
The local renderer prompts for an ACME contact without echo and writes mode0600
files to a **new** ignored directory. It makes no network request. The checked-in
IngressRoute has an invalid example hostname and must be rendered first.
An existing private overlay can be supplied with --contact-file. The CA receives
the contact on issuance. Do not export contact overlays, ACME/TLS keys or Helm secrets.

```bash
export GPU_HOST='NEW_VM_IP'
export INFERENCE_HOST='CURRENT_HOSTNAME'
python3 scripts/cloud/prepare_https.py --host "$GPU_HOST" \
  --hostname "$INFERENCE_HOST" --output-dir .private/https-current
curl -fL https://traefik.github.io/charts/traefik/traefik-42.1.3.tgz \
  -o .private/vendor/traefik-42.1.3.tgz
printf '%s  %s\n' 10ec2b032fd7ec9fa04a8816872e20ba0fafc47231f6394b5cb5d522f3b0ef50 \
  .private/vendor/traefik-42.1.3.tgz | sha256sum -c -
getent ahostsv4 "$INFERENCE_HOST"
```

Proceed only after checksum success and DNS resolves to the current VM.
A new IP needs a new render; this profile assumes IPv4 and a single DNS destination.
Check that host ports80/443 are free before installation.

```bash
.private/bin/helm upgrade --install sglang-edge .private/vendor/traefik-42.1.3.tgz \
  --kubeconfig .private/cloud-kubeconfig --kube-context k3s-sglang-platform \
  --namespace sglang-platform --values deploy/k3s/traefik-values.yaml \
  --values .private/https-current/traefik-contact.json --wait --timeout 5m
ssh -i ~/.ssh/sglang_lab_ed25519 "ubuntu@$GPU_HOST" \
  'sudo -n ufw allow 80/tcp && sudo -n ufw allow 443/tcp'
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -f .private/https-current/inference-ingress.yaml
python3 scripts/acceptance/https.py --host "$GPU_HOST" \
  --base-url "https://$INFERENCE_HOST" --run-inference
```

Install Traefik, open80/443, then apply the route so HTTP-01 starts after the firewall
is ready. Port80 is ACME-only; no model key is sent over HTTP. HTTPS permits only
POST /generate, /v1/chat/completions and /v1/completions. The helper checks trusted
TLS, missing/wrong-key rejection, private route/port isolation and one16-token
native generation; it rejects redirects and checks cluster/DNS against the host.

One Traefik Pod uses host80/443 and persistent local ACME storage; it is a single
point of failure. Configured limits16 active,8/s,burst16 are not measured capacity.
Renewal/restart, the two OpenAI request shapes, rate-rejection and complete
application-log redaction remain untested. See [evidence](presentation.md).

For an incorrect route restore the last accepted rendered route/Helm values.
Do not widen the allowlist or expose backend ports to troubleshoot. Deleting the
IngressRoute does not destroy the paid VM: retain evidence, explicitly destroy
the VM at the provider and confirm its state.
