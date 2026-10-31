#!/usr/bin/env python3
"""One explicit current GPU VM -> authenticated HTTPS serving with replica autoscaling."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import getpass
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import ssl
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

import cloud
import prepare_https

ROOT = Path(__file__).resolve().parents[2]
OWNER = 'sglang.lab/bootstrap-owner'
ARTIFACTS = {
    'helm-v3.22.1-linux-amd64.tar.gz': (
        'https://get.helm.sh/helm-v3.22.1-linux-amd64.tar.gz',
        '896cf63684a42a723d61c980369d6e588330927deb13676ca0d85006dd6da0ea'),
    'keda-2.21.0.tgz': (
        'https://kedacore.github.io/charts/keda-2.21.0.tgz',
        'a7da56bf41a33dad9d2fc82a6fdecee552fff947d80bf1e1dbcf4db0f9e26dee'),
    'traefik-42.1.3.tgz': (
        'https://traefik.github.io/charts/traefik/traefik-42.1.3.tgz',
        '10ec2b032fd7ec9fa04a8816872e20ba0fafc47231f6394b5cb5d522f3b0ef50'),
}
STAGES = ['render', 'tools', 'host', 'apps', 'preflight', 'autoscaling', 'edge', 'firewall', 'route', 'tls', 'external']


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix='.launch-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def source_digest():
    paths = sorted(p for directory in ['scripts/cloud', 'scripts/acceptance', 'deploy/k3s']
                   for p in (ROOT/directory).rglob('*')
                   if p.is_file() and p.suffix in ('.py', '.sh', '.yaml', '.yml'))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()


@contextmanager
def deployment_lock(path):
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY|os.O_CREAT, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another launcher is active for this host; no concurrent deployment.')
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class Checkpoint:
    def __init__(self, path, identity, source_sha, resume):
        self.path = path
        if path.exists():
            if not resume:
                raise RuntimeError('A launch record exists. Inspect it and use --resume for the same VM.')
            self.data = json.loads(path.read_text())
            if self.data.get('identity') != identity or self.data.get('source_sha') != source_sha:
                raise RuntimeError('Saved target/configuration differs. Resume refused; do not overwrite its record.')
        else:
            if resume:
                raise RuntimeError('No launch record exists for --resume.')
            if path.parent.exists() and any(path.parent.iterdir()):
                raise RuntimeError('Unowned deployment directory already exists; no adoption.')
            self.data = {'schema': 1, 'identity': identity, 'source_sha': source_sha,
                         'owner': uuid.uuid4().hex, 'cluster_uid': None, 'namespace_uid': None,
                         'done': [], 'in_progress': None}
            self.save()

    def save(self):
        atomic(self.path, (json.dumps(self.data, indent=2)+'\n').encode())

    def stage(self, name, action):
        if name in self.data['done']:
            print('SKIP accepted stage: '+name, flush=True)
            return
        self.data['in_progress'] = name
        self.save()
        print('START '+name, flush=True)
        action()
        self.data['done'].append(name)
        self.data['in_progress'] = None
        self.data['updated_utc'] = datetime.now(timezone.utc).isoformat()
        self.save()
        print('DONE '+name, flush=True)

    def bind_cluster(self, uid):
        if not uid or (self.data['cluster_uid'] is not None and self.data['cluster_uid'] != uid):
            raise RuntimeError('Cluster identity changed; no resume/application changes allowed.')
        self.data['cluster_uid'] = uid
        self.save()


def fetch_verified(path, url, digest):
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Cached artifact checksum mismatch; no overwrite or extraction.')
        return
    with urllib.request.urlopen(url, timeout=60) as response:
        if not response.geturl().startswith('https://'):
            raise RuntimeError('Artifact download left HTTPS.')
        blob = response.read(100*1024*1024+1)
    if len(blob) > 100*1024*1024 or hashlib.sha256(blob).hexdigest() != digest:
        raise RuntimeError('Downloaded artifact checksum mismatch; not installed.')
    atomic(path, blob)


def prepare_tools():
    vendor = ROOT/'.private/vendor'
    for name, (url, digest) in ARTIFACTS.items():
        fetch_verified(vendor/name, url, digest)
    with tarfile.open(vendor/'helm-v3.22.1-linux-amd64.tar.gz', 'r:gz') as tar:
        member = tar.getmember('linux-amd64/helm')
        if not member.isfile() or member.size > 100*1024*1024:
            raise RuntimeError('Unexpected Helm archive member.')
        binary = tar.extractfile(member).read()
    helm = ROOT/'.private/bin/helm'
    if helm.exists() and helm.read_bytes() != binary:
        raise RuntimeError('Existing Helm binary differs; no overwrite.')
    if not helm.exists():
        atomic(helm, binary, 0o700)


def verify_tools():
    for name, (_, digest) in ARTIFACTS.items():
        path = ROOT/'.private/vendor'/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Prepared artifact changed or disappeared; no deployment.')
    with tarfile.open(ROOT/'.private/vendor/helm-v3.22.1-linux-amd64.tar.gz','r:gz') as tar:
        binary = tar.extractfile('linux-amd64/helm').read()
    if (ROOT/'.private/bin/helm').read_bytes() != binary:
        raise RuntimeError('Prepared Helm binary changed; no execution.')


def read(extra):
    return json.loads(cloud.run(cloud.k(*extra), capture=True))


def verify_saved_cluster(a, cp):
    uid = cp.data['cluster_uid']
    if uid is None:
        return
    actual = cloud.run(cloud.ssh(a, 'sudo -n k3s kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml '
        '--context default get namespace kube-system -o jsonpath={.metadata.uid}'), capture=True).decode()
    if actual != uid:
        raise RuntimeError('SSH cluster changed since the saved run; no host/app changes performed.')


def claim_namespace(cp):
    raw = cloud.run(cloud.k('get', 'namespace', cloud.NS, '--ignore-not-found', '-o', 'json'), capture=True)
    if not raw.strip():
        if cp.data['namespace_uid'] is not None:
            raise RuntimeError('Owned namespace disappeared; do not recreate automatically.')
        manifest = {'apiVersion': 'v1', 'kind': 'Namespace',
            'metadata': {'name': cloud.NS, 'annotations': {OWNER: cp.data['owner']}}}
        # Create, never adopt/overwrite another namespace.
        cloud.run(cloud.k('create', '-f', '-'), data=json.dumps(manifest).encode(), capture=True)
        namespace = read(['get', 'namespace', cloud.NS, '-o', 'json'])
    else:
        namespace = json.loads(raw)
    meta = namespace['metadata']
    if meta.get('annotations', {}).get(OWNER) != cp.data['owner']:
        raise RuntimeError('Namespace is not owned by this launch record; no adoption.')
    if cp.data['namespace_uid'] not in (None, meta['uid']):
        raise RuntimeError('Namespace identity changed; resume refused.')
    cp.data['namespace_uid'] = meta['uid']
    cp.save()


def render_inputs(a, cp, directory):
    # Save file hashes before publishing the directory; lost acknowledgements are resumable.
    if cp.data.get('input_hashes'):
        if not directory.exists():
            pending = directory.parent/cp.data['render_pending']
            verify_inputs(cp, pending)
            os.rename(pending, directory)
        verify_inputs(cp, directory)
        return
    if directory.exists():
        raise RuntimeError('Unrecorded HTTPS directory exists; no overwrite.')
    if a.contact_file:
        email = json.loads(a.contact_file.read_text())['certificatesResolvers']['le']['acme']['email']
    else:
        email = getpass.getpass('ACME contact email (private; sent to CA for issuance): ').strip()
    pending = directory.with_name('https-preparing-'+uuid.uuid4().hex[:12])
    prepare_https.render(a.host, a.hostname, pending, email)
    cp.data['input_hashes'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in pending.iterdir() if p.is_file()}
    cp.data['render_pending'] = pending.name
    cp.save()
    os.rename(pending, directory)


def verify_inputs(cp, directory):
    for name, digest in cp.data.get('input_hashes', {}).items():
        path = directory/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Saved private HTTPS input changed; inspect instead of rerendering.')
    if not cp.data.get('input_hashes'):
        raise RuntimeError('No complete HTTPS render recorded; inspect partial local input directory.')


def dns_matches(a):
    addresses = {x[4][0] for x in socket.getaddrinfo(a.hostname, 443, type=socket.SOCK_STREAM)}
    if addresses != {a.host}:
        raise RuntimeError('HTTPS DNS must exclusively resolve to the explicit current IPv4.')


def acceptance(a, tool, flags):
    return cloud.run([sys.executable, ROOT/'scripts/acceptance'/tool, '--host', a.host,
               '--kubeconfig', cloud.KUBECONFIG, '--context', cloud.CONTEXT, *flags],
              capture=True, timeout=240)


def enable_scaling():
    cloud.run(cloud.k('apply', '-f', ROOT/'deploy/k3s/sglang-scaledobject.yaml'))
    cloud.run(cloud.k('wait', '--for=condition=Ready', 'scaledobject/sglang-worker-load',
                      '--timeout=120s'), timeout=150)
    cloud.run(cloud.k('wait', '--for=create', 'hpa/sglang-worker-hpa', '--timeout=120s'), timeout=150)
    cond = {x['type']: x['status'] for x in read(['get','scaledobject','sglang-worker-load','-o','json']).get('status',{}).get('conditions',[])}
    if cond.get('Ready') != 'True' or cond.get('Fallback') == 'True':
        raise RuntimeError('Autoscaler is not ready without fallback.')


def install_edge(directory):
    cloud.run([ROOT/'.private/bin/helm', 'upgrade', '--install', 'sglang-edge',
        ROOT/'.private/vendor/traefik-42.1.3.tgz', '--kubeconfig', cloud.KUBECONFIG,
        '--kube-context', cloud.CONTEXT, '--namespace', cloud.NS,
        '--values', ROOT/'deploy/k3s/traefik-values.yaml',
        '--values', directory/'traefik-contact.json', '--wait', '--timeout', '5m'],
        capture=True, timeout=330)


def wait_tls(a, seconds=300):
    deadline = time.monotonic()+seconds
    while True:
        try:
            context = ssl.create_default_context()
            with socket.create_connection((a.hostname,443), timeout=5) as raw:
                with context.wrap_socket(raw, server_hostname=a.hostname):
                    return
        except (OSError, ssl.SSLError):
            if time.monotonic() >= deadline:
                raise RuntimeError('Trusted TLS did not become ready; preserve resources and inspect ACME/DNS.')
            time.sleep(5)


def final_checks(a, seconds=90):
    deadline = time.monotonic()+seconds
    while True:
        output = acceptance(a, 'ready.py', ['--snapshot-only'])
        value = json.loads(output.decode().splitlines()[-1])
        scaler = read(['get','scaledobject','sglang-worker-load','-o','json'])
        cond = {x['type']:x['status'] for x in scaler.get('status',{}).get('conditions',[])}
        if (value['gateway_status'] == 200 and value['healthy_urls']
                and value['rule_state'] == 'inactive' and value['rule_health'] == 'ok'
                and value['alertmanager_status'] == 200 and cond.get('Ready') == 'True'
                and cond.get('Fallback') == 'False' and cond.get('Paused') != 'True'):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('Final serving/alert/scaler baseline not healthy; launch not accepted.')
        time.sleep(3)


def pipeline(a, cp, directory):
    external_previously_done = 'external' in cp.data['done']
    preflight_previously_done = 'preflight' in cp.data['done']
    verify_saved_cluster(a, cp)  # Before installing/rechecking a host on resumed runs.
    cp.stage('render', lambda: render_inputs(a, cp, directory))
    verify_inputs(cp, directory)
    cp.stage('tools', prepare_tools)
    verify_tools()
    dns_matches(a)
    cp.stage('host', lambda: cloud.host(a))
    with cloud.tunnel(a):
        cloud.connect(a)
        uid = read(['get', 'namespace', 'kube-system', '-o', 'json'])['metadata']['uid']
        cp.bind_cluster(uid)
        node = read(['get', 'node', 'sglang-gpu-01', '-o', 'json'])
        if not any(x.get('address') == a.host for x in node['status']['addresses']):
            raise RuntimeError('Tunnel node address does not match --host.')
        claim_namespace(cp)
        cp.stage('apps', lambda: cloud.deploy(a, owner=cp.data['owner']))
        cp.stage('preflight', lambda: acceptance(a, 'ready.py', ['--run-inference']))
        # Recheck the auth gate before any resumed exposure, even if preflight was previously done.
        if preflight_previously_done:
            acceptance(a, 'ready.py', ['--run-inference'])
        cp.stage('autoscaling', enable_scaling)
        cp.stage('edge', lambda: install_edge(directory))
        cp.stage('firewall', lambda: cloud.run(cloud.ssh(a,
            'sudo -n ufw allow 80/tcp && sudo -n ufw allow 443/tcp'), capture=True))
        cp.stage('route', lambda: cloud.run(cloud.k('apply', '-f', directory/'inference-ingress.yaml')))
        cp.stage('tls', lambda: wait_tls(a))
        cp.stage('external', lambda: acceptance(a, 'https.py',
            ['--base-url', 'https://'+a.hostname, '--run-inference']))
        # Previously accepted stages are not proof of current external/serving health.
        if external_previously_done:
            wait_tls(a)
            acceptance(a, 'https.py', ['--base-url', 'https://'+a.hostname, '--run-inference'])
        final_checks(a)
    print('READY: https://'+a.hostname, flush=True)
    print('Small internal/external checks passed; replica autoscaling enabled (1-2). '
          'No load/failure experiment performed. API tunnel now closed. '
          'Key remains in .private/cloud-engine.key; value not displayed. VM is still billable.', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', required=True, help='Explicit NEW dedicated VM IPv4')
    p.add_argument('--hostname', help='DNS hostname; defaults to IP-encoded sslip.io')
    p.add_argument('--contact-file', type=Path, help='Private ACME JSON overlay; otherwise hidden local prompt')
    p.add_argument('--resume', action='store_true', help='Continue this record only; cluster/namespace/source identity must match')
    p.add_argument('--plan', action='store_true', help='Print stages only; no downloads, files, SSH or cluster access')
    p.add_argument('--user', default='ubuntu')
    p.add_argument('--key', default=str(Path.home()/'.ssh/sglang_lab_ed25519'))
    p.add_argument('--ssh-port', type=int, default=22)
    p.add_argument('--api-port', type=int, default=16443)
    a = p.parse_args()
    a.host = str(ipaddress.IPv4Address(a.host))
    a.hostname = a.hostname or 'sglang-'+a.host.replace('.','-')+'.sslip.io'
    if not re.fullmatch(r'(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',a.hostname) or any(
            not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',x) for x in a.hostname.split('.')):
        p.error('Use a valid lowercase hostname')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*',a.user) or not all(0<x<65536 for x in [a.ssh_port,a.api_port]):
        p.error('Invalid user/ports')
    if a.plan:
        print(json.dumps({'host':a.host,'hostname':a.hostname,'stages':STAGES,
            'public_ports':[80,443],'smoke':'one internal and one external 16-token request',
            'autoscaling':'min1/max2; existing GPUs only','resource_purchase':False,
            'load_or_failure_experiments':False,'automatic_teardown':False},indent=2))
        return
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64','amd64'):
        p.error('Run from Linux/WSL amd64')
    for tool in ['ssh','kubectl']:
        if shutil.which(tool) is None:
            p.error('Install local prerequisite: '+tool)
    a.key = str(Path(a.key).expanduser().resolve())
    if not Path(a.key).is_file():
        p.error('SSH key file is missing; establish SSH host trust before launching')
    os.umask(0o077)
    location = ROOT/'.private/deployments'/a.host
    identity = {'host':a.host,'hostname':a.hostname,'user':a.user,'ssh_port':a.ssh_port}
    with deployment_lock(ROOT/'.private/deployments/.locks'/(a.host+'.lock')):
        cp = Checkpoint(location/'state.json', identity, source_digest(), a.resume)
        print('Private stage record: '+str(cp.path), flush=True)
        pipeline(a, cp, location/'https')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit('Stopped; resources remain allocated. Inspect the stage record, then --resume for the same VM.')
    except RuntimeError as error:
        sys.exit('Launch stopped: '+str(error)+' No automatic teardown; resources may still be billable.')
    except Exception as error:
        sys.exit('Launch stopped: '+type(error).__name__+'; private details withheld. '
                 'Inspect the last stage, fix its prerequisite and --resume only for the same VM. '
                 'No automatic teardown; the VM may still be billable.')
