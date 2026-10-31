import json
from pathlib import Path
import secrets
import socket
import ssl
import urllib.error
import urllib.request

from common import add_target_arguments, configure_target, private_key, run_main

HOST=None
IP=None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward Bearer credentials to another URL.
        return None


def main():
    import argparse
    import urllib.parse
    p=argparse.ArgumentParser(description='Trusted external HTTPS, auth/path/port isolation and one16-token generation')
    add_target_arguments(p,public=True)
    p.add_argument('--run-inference',action='store_true')
    a=p.parse_args()
    if not a.run_inference: p.error('Pass --run-inference for bounded public generation')
    global HOST,IP
    target=configure_target(a,public=True);HOST=urllib.parse.urlsplit(target.base_url).hostname;IP=a.host
    context = ssl.create_default_context()
    with socket.create_connection((HOST, 443), timeout=10) as connection:
        with context.wrap_socket(connection, server_hostname=HOST) as tls:
            cert = tls.getpeercert()
            print('TLS verified:', tls.version(), 'expires:', cert.get('notAfter'), flush=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=context))
    key = private_key(target.key_file)
    assert key, 'Private engine key file is empty'

    def call(scheme, path, credential=None, body=None):
        assert credential is None or scheme == 'https', 'Never send credentials over HTTP'
        headers = {'Content-Type': 'application/json'}
        if credential is not None:
            headers['Authorization'] = 'Bearer ' + credential
        req = urllib.request.Request(scheme + '://' + HOST + path, headers=headers,
            data=None if body is None else json.dumps(body).encode())
        try:
            with opener.open(req, timeout=120) as response:
                payload = response.read()
                return response.status, json.loads(payload) if payload else None
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            return status, None

    for label, credential in [('missing key', None), ('wrong key', secrets.token_hex(32))]:
        status, _ = call('https', '/generate', credential, {})
        print(label + ':', status, flush=True)
        assert status in (401, 403), label + ' was not rejected'
    for path in ['/workers', '/metrics', '/engine_metrics', '/get_server_info',
                 '/server_info', '/v1/models', '/dashboard/', '/api/rawdata']:
        status, _ = call('https', path, key)
        print('private path:', path, status, flush=True)
        assert status == 404, 'Management/metadata route exposed: ' + path
    for path in ['/metrics', '/v1/models']:
        status, _ = call('https', path, key, {})
        assert status == 404, 'Unexpected public POST path: ' + path
    status, _ = call('http', '/generate', None, {})
    print('plaintext inference:', status, flush=True)
    assert status == 404, 'Unexpected plaintext inference route'
    for port in [30000, 8080, 9090, 6443]:
        with socket.socket() as probe:
            probe.settimeout(2)
            result = probe.connect_ex((IP, port))
        assert result != 0, 'Private backend/management TCP port reachable: ' + str(port)
        print('private TCP port:', port, 'unreachable from this client', flush=True)
    status, generated = call('https', '/generate', key, {
        'text': 'The capital of France is',
        'sampling_params': {'max_new_tokens': 16, 'temperature': 0, 'ignore_eos': True},
        'stream': False,
    })
    assert status == 200 and generated.get('meta_info', {}).get('completion_tokens') == 16
    print('external generation:', status, 'completion_tokens:', generated['meta_info']['completion_tokens'], flush=True)
    print('PASS: trusted HTTPS, missing/wrong key rejected, private routes/ports isolated, authenticated external inference', flush=True)


if __name__ == '__main__':
    run_main(main)
