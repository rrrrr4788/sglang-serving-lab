[English](acceptance.md) | [简体中文](acceptance.zh-CN.md)

# Public acceptance tools

Python3.10+ standard-library tools run from WSL/Linux repository root. They require
an authorized current dedicated VM and API tunnel. No private lab source files are
required; key, kubeconfig, generated files and evidence remain ignored.
No node purchasing, VM deletion or automatic ScaledObject activation is included.

Every tool requires --host. Kubeconfig/context/namespace are explicit; node address
must match the supplied IPv4. Public checks additionally require a trusted HTTPS
root --base-url whose DNS exclusively matches that host. Namespace is fixed to
sglang-platform. Defaults are the named project context and private key/kubeconfig,
never a saved host. See --help for --context/--kubeconfig/--node/--key-file/
--evidence-dir. Evidence must remain under .private; key permissions must be0600.

Initialize the VM and pass preflight before applying the scaler. Complete
[HTTPS installation](https.md) before external/stream checks:

```bash
export GPU_HOST='NEW_VM_IP'
export INFERENCE_URL='https://CURRENT_HOSTNAME'
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --run-inference
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -f deploy/k3s/sglang-scaledobject.yaml
python3 scripts/acceptance/autoscaling.py --host "$GPU_HOST" --run-load
python3 scripts/acceptance/https.py --host "$GPU_HOST" \
  --base-url "$INFERENCE_URL" --run-inference
python3 scripts/acceptance/stream_cancel.py --host "$GPU_HOST" \
  --base-url "$INFERENCE_URL" --run-inference
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --snapshot-only
```

| Tool | Bound and interpretation |
| --- | --- |
| ready --run-inference | Auth rejection,TP1/DP1,Gateway,16-token generation,one idle guarded metric |
| autoscaling --run-load | 8 closed-loop clients,max256 requests or300s admission,64 input/2048 output;900s observer;1→2→1,distinct GPUs,both serving,idle process release |
| https --run-inference | Trusted TLS,auth/private routes/ports and16-token native generation |
| stream_cancel --run-inference | Complete128-token SSE,early close of3500-token request;150s total;abort signal plus two idle samples |
| ready --snapshot-only | Read-only Gateway/rule/Alertmanager/receiver; no inference |
| operations --run-maintenance | Planned single-replica outage; [recovery runbook](operations.md) |

Autoscaling also uses SSH GPU-process inspection; --ssh-user/--ssh-key/--ssh-port
override bootstrap defaults. No unrelated GPU jobs may run on the dedicated host.
Stopping the observer does not prove the remote bounded client has already stopped.
Do not overlap checks, manually scale during load or run with python -O.
Generation, load and maintenance require explicit execution flags.

JSONL/recovery files go to .private/evidence. Preflight/HTTPS print selected results;
use a private tee file and pipefail to retain stdout. Keys, raw K8s errors and
generated text are not printed. Missing observations remain FAIL even if recovery
restores serving.

Historical reports used the original lab helpers on the recorded hardware.
These public parameterized tools were derived from them and tested **offline**,
not rerun on a fresh GPU VM. CLI/target/DNS/SSE/recovery tests do not replace
runtime GPU acceptance. New environments need dated evidence; original hashes stay unchanged.
