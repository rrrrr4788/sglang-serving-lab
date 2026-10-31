#!/usr/bin/env python3
"""Explicit cloud rebuild stages; run from WSL/Linux, never the destroyed host by default."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / '.private'
KUBECONFIG = PRIVATE / 'cloud-kubeconfig'
CONTEXT = 'k3s-sglang-platform'
NS = 'sglang-platform'
CHART_SHA = 'a7da56bf41a33dad9d2fc82a6fdecee552fff947d80bf1e1dbcf4db0f9e26dee'


def fail(message):
    raise RuntimeError(message)


def run(args, *, data=None, capture=False, timeout=120):
    result = subprocess.run([str(x) for x in args], input=data, stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None, timeout=timeout)
    if result.returncode:
        # Captured commands may contain credentials in stdout/stderr. Never echo either.
        fail(f'{Path(str(args[0])).name} failed (exit {result.returncode}); captured output withheld.')
    return result.stdout if capture else None


def ssh(a, command):
    return ['ssh', '-i', a.key, '-p', str(a.ssh_port), '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            f'{a.user}@{a.host}', command]


def k(*args, namespace=NS):
    return ['kubectl', '--kubeconfig', KUBECONFIG, '--context', CONTEXT,
            '--namespace', namespace, *args]


def private_write(path, data):
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.cloud-', dir=PRIVATE)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def host(a):
    names = ['scripts/cloud/bootstrap-host.sh', 'deploy/k3s/k3s-server.yaml',
             'deploy/k3s/nvidia-device-plugin.yaml']
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as tar:
        for name in names:
            tar.add(ROOT / name, arcname=name, recursive=False)
    command = ('set -eu; task_dir=$(mktemp -d /tmp/sglang-bootstrap.XXXXXXXX); '
               'trap \'rm -rf -- "$task_dir"\' EXIT; '
               'tar -xf - -C "$task_dir"; sudo -n bash "$task_dir/scripts/cloud/bootstrap-host.sh" '
               + str(a.ssh_port))
    run(ssh(a, command), data=archive.getvalue(), timeout=1200)


@contextmanager
def tunnel(a):
    # Never reuse an unknown listener: it might point to a different cluster.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', a.api_port))
        except OSError:
            fail(f'Local port {a.api_port} is occupied; stop its old tunnel or choose --api-port.')
    # ssh() includes the destination; rebuild options without duplicating it.
    cmd = ssh(a, '')[:-2] + ['-N', '-o', 'ExitOnForwardFailure=yes', '-L',
                            f'127.0.0.1:{a.api_port}:127.0.0.1:6443', f'{a.user}@{a.host}']
    process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if process.poll() is not None:
                fail('SSH tunnel exited before becoming ready.')
            try:
                with socket.create_connection(('127.0.0.1', a.api_port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            fail('SSH tunnel did not become ready within 10 seconds.')
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def connect(a):
    raw = run(ssh(a, 'sudo -n k3s kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml '
                  '--context default config view --raw -o json'), capture=True)
    cfg = json.loads(raw)
    if not all(len(cfg.get(name, [])) == 1 for name in ['clusters', 'contexts', 'users']):
        fail('Unexpected remote kubeconfig structure.')
    cfg['clusters'][0]['cluster']['server'] = f'https://127.0.0.1:{a.api_port}'
    cfg['clusters'][0]['name'] = CONTEXT
    cfg['users'][0]['name'] = CONTEXT
    cfg['contexts'][0] = {'name': CONTEXT, 'context': {'cluster': CONTEXT, 'user': CONTEXT}}
    cfg['current-context'] = CONTEXT
    remote_uid = run(ssh(a, 'sudo -n k3s kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml '
                         '--context default get namespace kube-system -o jsonpath={.metadata.uid}'), capture=True).decode()
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.cloud-check-', dir=PRIVATE) as temporary:
        temporary.write(json.dumps(cfg).encode())
        temporary.flush()
        local = json.loads(run(['kubectl', '--kubeconfig', temporary.name, '--context', CONTEXT,
                                '--namespace', NS, 'get', 'namespace', 'kube-system', '-o', 'json'], capture=True))
    if not remote_uid or local['metadata']['uid'] != remote_uid:
        fail('Tunnel cluster identity differs from the SSH target; previous kubeconfig preserved.')
    if KUBECONFIG.exists():
        backup = PRIVATE / ('cloud-kubeconfig.backup-' + secrets.token_hex(4))
        private_write(backup, KUBECONFIG.read_bytes())
    private_write(KUBECONFIG, json.dumps(cfg).encode())
    print('Private kubeconfig imported; cluster identity matched. No credentials displayed.', flush=True)


def deploy(a, *, owner=None):
    helm = ROOT / '.private/bin/helm'
    chart = ROOT / '.private/vendor/keda-2.21.0.tgz'
    if not helm.is_file() or not chart.is_file():
        fail('Prepare .private/bin/helm and the fixed KEDA chart first; see cloud-rebuild.md.')
    if hashlib.sha256(chart.read_bytes()).hexdigest() != CHART_SHA:
        fail('KEDA chart checksum mismatch.')
    # This initializer is for a new cluster. Never switch/restart a live serving profile.
    deployments = json.loads(run(k('get', 'deployments', '-A', '-o', 'json'), capture=True))
    project = [x for x in deployments['items'] if x['metadata']['namespace'] == NS]
    if owner is None and project:
        fail('Project Deployments already exist. Initialization stopped; inspect rather than reapply.')
    if owner is not None:
        namespace = json.loads(run(k('get', 'namespace', NS, '-o', 'json'), capture=True))
        if namespace['metadata'].get('annotations', {}).get('sglang.lab/bootstrap-owner') != owner:
            fail('Resume namespace ownership differs; no application changes performed.')
        allowed = {'sglang-worker', 'sglang-gateway', 'sglang-prometheus',
                   'sglang-alertmanager', 'sglang-alert-receiver', 'sglang-edge-traefik'}
        if any(x['metadata']['name'] not in allowed for x in project):
            fail('Unexpected workload in owned namespace; inspect before resuming.')
        raw_keda = run(k('get', 'namespace', 'keda', '--ignore-not-found', '-o', 'json'), capture=True)
        if raw_keda.strip():
            keda_namespace = json.loads(raw_keda)
            if keda_namespace['metadata'].get('annotations', {}).get('sglang.lab/bootstrap-owner') != owner:
                fail('KEDA namespace belongs to another installation; no adoption or upgrade.')
        else:
            keda_namespace = {'apiVersion': 'v1', 'kind': 'Namespace',
                              'metadata': {'name': 'keda', 'annotations': {'sglang.lab/bootstrap-owner': owner}}}
            run(k('create', '-f', '-'), data=json.dumps(keda_namespace).encode(), capture=True)
    external = json.loads(run(k('get', 'apiservices', '-o', 'json'), capture=True))
    existing = [x for x in external['items'] if x['metadata']['name'] == 'v1beta1.external.metrics.k8s.io']
    if existing:
        service = existing[0].get('spec', {}).get('service', {})
        if owner is None or service.get('namespace') != 'keda' or service.get('name') != 'keda-operator-metrics-apiserver':
            fail('External metrics API already owned by another stack; inspect before installing KEDA.')
    run(k('apply', '-f', ROOT / 'deploy/k3s/namespace-storage.yaml'))
    keyfile = PRIVATE / 'cloud-engine.key'
    if not keyfile.exists():
        private_write(keyfile, secrets.token_hex(32).encode())
    if keyfile.stat().st_mode & 0o077:
        fail('cloud-engine.key must have mode 0600 (chmod 600 it locally).')
    key = keyfile.read_bytes().strip()
    if not re.fullmatch(rb'[0-9a-f]{64}', key):
        fail('Expected the existing 64-hex-character engine key; value not displayed.')
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'sglang-engine-auth', 'namespace': NS},
              'type': 'Opaque', 'data': {'api-key': base64.b64encode(key).decode()}}
    # Server-side apply avoids embedding a second key copy in last-applied annotations.
    run(k('apply', '--server-side', '--field-manager=sglang-bootstrap', '-f', '-'),
        data=json.dumps(secret).encode(), capture=True)
    print('Private engine Secret provisioned; value not displayed.', flush=True)
    run(k('apply', '-k', ROOT / 'deploy/k3s/operations'))
    for name in ['gateway-rbac.yaml', 'worker-autoscale.yaml', 'gateway.yaml', 'prometheus.yaml']:
        run(k('apply', '-f', ROOT / 'deploy/k3s' / name))
    for name, timeout in [('sglang-worker', 1200), ('sglang-gateway', 300), ('sglang-prometheus', 180),
                          ('sglang-alertmanager', 180), ('sglang-alert-receiver', 180)]:
        run(k('rollout', 'status', 'deployment/' + name, f'--timeout={timeout}s'), timeout=timeout + 30)
    run([helm, 'upgrade', '--install', 'keda', chart, '--kubeconfig', KUBECONFIG,
         '--kube-context', CONTEXT, '--namespace', 'keda', '--create-namespace',
         '--values', ROOT / 'deploy/k3s/keda-values.yaml', '--wait', '--timeout', '5m'], timeout=330)
    run(k('wait', '--for=condition=Available', 'apiservice/v1beta1.external.metrics.k8s.io', '--timeout=120s'), timeout=150)
    print('Initialization completed: worker/Gateway/Prometheus Ready and KEDA available.\n'
          'ScaledObject is intentionally not applied. Inference, metric values and real GPU scaling still need acceptance.\n'
          'The temporary API tunnel will close now. Use the tunnel subcommand for subsequent kubectl access.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['host', 'deploy', 'tunnel'], help='host: firewall/K3s/GPU; deploy: import config and initial app stack; tunnel: foreground API access')
    parser.add_argument('--host', required=True, help='Explicit new VM address; no saved/default host')
    parser.add_argument('--user', default='ubuntu')
    parser.add_argument('--key', default=str(Path.home() / '.ssh/sglang_lab_ed25519'))
    parser.add_argument('--ssh-port', type=int, default=22)
    parser.add_argument('--api-port', type=int, default=16443)
    a = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', a.host) or not re.fullmatch(r'[a-z_][a-z0-9_-]*', a.user):
        parser.error('Use an IPv4 address or DNS name and a standard Linux username.')
    if not all(0 < value < 65536 for value in [a.ssh_port, a.api_port]):
        parser.error('Ports must be 1..65535.')
    a.key = str(Path(a.key).expanduser().resolve())
    if not Path(a.key).is_file():
        parser.error('SSH private key file does not exist.')
    os.umask(0o077)
    if a.stage == 'host':
        host(a)
    else:
        with tunnel(a) as process:
            connect(a)
            if a.stage == 'deploy':
                deploy(a)
            else:
                print(f'API tunnel active on 127.0.0.1:{a.api_port}; Ctrl-C closes it.', flush=True)
                process.wait()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Stopped. Cloud VM remains allocated and billable.', file=sys.stderr)
        sys.exit(130)
    except RuntimeError as error:
        print(str(error) + '\nStopped; resources remain allocated. No automatic teardown.', file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Avoid dumping credential-bearing CalledProcessError objects or kubeconfig bodies.
        print('Cloud stage failed; existing resources are preserved. Check prerequisites and the last visible stage.\n'
              'No automatic teardown or retry was performed. The VM may still be billable.', file=sys.stderr)
        sys.exit(1)
