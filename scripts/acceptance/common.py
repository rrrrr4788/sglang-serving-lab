import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
from types import SimpleNamespace
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PAYLOADS = Path(__file__).resolve().parent / 'payloads'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def sse_events(response):
    data = []
    for raw in response:
        line = raw.decode('utf-8').rstrip('\r\n')
        if not line:
            if data:
                payload = '\n'.join(data); data = []
                if payload == '[DONE]':
                    yield None; return
                event = json.loads(payload)
                if 'error' in event: raise RuntimeError('SSE error event')
                yield event
        elif line.startswith('data:'):
            data.append(line[5:].lstrip())
    if data: raise RuntimeError('Truncated SSE frame')


def add_target_arguments(parser, public=False):
    parser.add_argument('--host', required=True, help='Explicit CURRENT dedicated VM IPv4; never reuse a destroyed host')
    parser.add_argument('--kubeconfig', type=Path, default=ROOT/'.private/cloud-kubeconfig')
    parser.add_argument('--context', default='k3s-sglang-platform')
    parser.add_argument('--node', default='sglang-gpu-01')
    parser.add_argument('--evidence-dir', type=Path, default=ROOT/'.private/evidence')
    parser.add_argument('--key-file', type=Path, default=ROOT/'.private/cloud-engine.key')
    if public: parser.add_argument('--base-url', required=True, help='Trusted HTTPS origin, no path/query/userinfo; must resolve to --host')


def https_origin(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.port not in (None,443)):
        raise ValueError('Expected a root HTTPS origin on port 443')
    return 'https://' + parsed.hostname


def configure_target(args, public=False):
    if not __debug__: raise RuntimeError('Do not run acceptance with python -O; assertions are acceptance checks')
    ipaddress.IPv4Address(args.host)
    if not args.context or args.context.startswith('-') or not re.fullmatch(r'[a-z0-9][a-z0-9.-]*',args.node):
        raise ValueError('Invalid explicit context or node')
    os.umask(0o077)
    base = ['kubectl','--kubeconfig',str(args.kubeconfig.resolve()),'--context',args.context,'-n','sglang-platform']
    def read(extra):
        p = subprocess.run(base+extra,capture_output=True,text=True,timeout=25)
        if p.returncode: raise RuntimeError('Cluster identity check failed; private output withheld')
        return json.loads(p.stdout)
    node = read(['get','node',args.node,'-o','json'])
    if not any(x.get('address') == args.host for x in node['status']['addresses']):
        raise RuntimeError('Selected context node does not match --host')
    cluster = read(['get','namespace','kube-system','-o','json'])['metadata']['uid']
    url = https_origin(args.base_url) if public else None
    if url:
        addresses={x[4][0] for x in socket.getaddrinfo(urllib.parse.urlsplit(url).hostname,443,type=socket.SOCK_STREAM)}
        if addresses != {args.host}: raise RuntimeError('HTTPS DNS does not exclusively match --host')
    evidence=args.evidence_dir.resolve()
    if not evidence.is_relative_to((ROOT/'.private').resolve()):
        raise ValueError('Evidence must stay under the ignored repository .private directory')
    evidence.mkdir(parents=True,exist_ok=True,mode=0o700)
    print(json.dumps({'kind':'target_verified','host':args.host,'context':args.context,'namespace':'sglang-platform','cluster_uid':cluster}),flush=True)
    return SimpleNamespace(base=base,evidence=evidence,key_file=args.key_file.resolve(),base_url=url)


def private_key(path):
    if path.stat().st_mode & 0o077: raise ValueError('API key file must be mode 0600')
    key=path.read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}',key): raise ValueError('Expected a private 64-hex engine key file')
    return key


def run_main(main):
    try: main()
    except KeyboardInterrupt: raise SystemExit('Interrupted; inspect evidence/recovery metadata. VM billing is unaffected.')
    except Exception as error: raise SystemExit('FAIL: '+type(error).__name__+'; private exception details withheld. Inspect the last evidence event.')
