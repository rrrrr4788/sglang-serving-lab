import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
key = os.environ['SGLANG_API_KEY']
gateway = 'http://sglang-gateway.sglang-platform.svc.cluster.local'
prometheus = 'http://sglang-prometheus.sglang-platform.svc.cluster.local:9090'

def call(base, path, credential=None, body=None):
    headers = {'Content-Type': 'application/json'}
    if credential is not None:
        headers['Authorization'] = 'Bearer ' + credential
    req = urllib.request.Request(base + path, headers=headers,
        data=None if body is None else json.dumps(body).encode())
    try:
        with opener.open(req, timeout=120) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None

for label, credential in [('missing key', None), ('wrong key', secrets.token_hex(32))]:
    # Empty invalid payload cannot start inference even if auth is misconfigured.
    status, _ = call(gateway, '/generate', credential, {})
    print(label, status, flush=True)
    assert status in (401, 403), label + ' was not rejected'
status, models = call(gateway, '/v1/models', key)
assert status == 200 and models.get('data'), 'Model listing failed'
status, info = call('http://127.0.0.1:30000', '/server_info', key)
assert status == 200
runtime = {name: info.get(name) for name in ['version', 'tp_size', 'dp_size', 'model_path']}
assert runtime['tp_size'] == 1 and runtime['dp_size'] == 1, runtime
print('runtime:', runtime, flush=True)
status, readiness = call(gateway, '/readiness')
assert status == 200 and readiness['healthy_workers'] == 1, 'Expected one healthy backend'
print('gateway:', readiness, flush=True)
status, generated = call(gateway, '/generate', key, {
    'text': 'The capital of France is',
    'sampling_params': {'max_new_tokens': 16, 'temperature': 0, 'ignore_eos': True},
    'stream': False,
})
assert status == 200 and generated['meta_info']['completion_tokens'] == 16
print('generation:', status, 'completion_tokens:', generated['meta_info']['completion_tokens'], flush=True)

def query(expression):
    status, result = call(prometheus, '/api/v1/query?' + urllib.parse.urlencode({'query': expression}))
    assert status == 200 and result['status'] == 'success', 'Prometheus query failed'
    return result['data']['result']

expression = 'sum(\n  sglang:num_running_reqs{job="sglang",pod_ready="true",tp_rank="0"}\n  + on(instance)\n  sglang:num_queue_reqs{job="sglang",pod_ready="true",tp_rank="0"}\n)\nand on() (min(up{job="sglang",pod_ready="true"}) == 1)\nand on() (\n  count(sglang:num_running_reqs{job="sglang",pod_ready="true",tp_rank="0"})\n  == count(up{job="sglang",pod_ready="true"})\n)\nand on() (\n  count(sglang:num_queue_reqs{job="sglang",pod_ready="true",tp_rank="0"})\n  == count(up{job="sglang",pod_ready="true"})\n)\n'
for attempt in range(12):
    targets = query('up{job="sglang",pod_ready="true"}')
    metric = query(expression)
    if (len(targets) == 1 and float(targets[0]['value'][1]) == 1
            and len(metric) == 1 and float(metric[0]['value'][1]) == 0):
        break
    time.sleep(5)
else:
    raise AssertionError('Expected one Ready scrape target and one idle scaling value of zero')
print('scrape:', [{'pod': x['metric'].get('pod'), 'up': x['value'][1]} for x in targets], flush=True)
print('running+queued:', metric[0]['value'][1], flush=True)
print('PASS: Gateway authentication/inference, TP1/DP1 and idle real-engine scaling metric')
