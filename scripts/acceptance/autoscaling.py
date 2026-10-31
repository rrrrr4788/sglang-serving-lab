import uuid
import argparse
import datetime
import json
from pathlib import Path
import queue
import re
import runpy
import subprocess
import threading
import time

from common import add_target_arguments, configure_target, PAYLOADS, run_main

BASE=[]
LAB=None
def VALIDATE(readiness, workers, expected_urls):
    expected = sorted(url.rstrip("/") for url in expected_urls)
    healthy = sorted(worker["url"].rstrip("/")
        for worker in workers["workers"] if worker.get("is_healthy") is True)
    assert expected and len(expected) == len(set(expected)), "expected Ready Pod URLs must be non-empty and unique"
    assert readiness.get("status") == "ready", "Gateway is not ready"
    assert readiness["healthy_workers"] == len(healthy), "readiness and worker list disagree"
    assert healthy == expected, f"healthy backend URLs differ from Ready Pod URLs: {healthy} != {expected}"
    return {"healthy_urls": healthy, "registered_total": readiness["total_workers"],
            "unhealthy_registered": len(workers["workers"])-len(healthy)}


def read(args):
    result = subprocess.run(BASE + args, capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise RuntimeError('Read-only Kubernetes observation failed; output withheld to protect credentials')
    return json.loads(result.stdout)


def pods():
    return [p for p in read(['get', 'pods', '-l', 'app=sglang-worker', '-o', 'json'])['items']
            if not p['metadata'].get('deletionTimestamp') and
            any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in p.get('status', {}).get('conditions', []))]


def state():
    items = {x['kind']: x for x in read(['get', 'hpa/sglang-worker-hpa', 'deployment/sglang-worker',
                                               'scaledobject/sglang-worker-load', '-o', 'json'])['items']}
    hpa = items['HorizontalPodAutoscaler'].get('status', {})
    dep = items['Deployment']
    cond = {x['type']: x['status'] for x in items['ScaledObject'].get('status', {}).get('conditions', [])}
    metric = (hpa.get('currentMetrics') or [{}])[0].get('external', {}).get('current', {})
    return {'hpa_desired': hpa.get('desiredReplicas'), 'hpa_current': hpa.get('currentReplicas'),
            'deployment_desired': dep['spec'].get('replicas', 1),
            'deployment_current': dep.get('status', {}).get('replicas', 0),
            'deployment_ready': dep.get('status', {}).get('readyReplicas', 0),
            'metric_average': metric.get('averageValue'), 'scaler_ready': cond.get('Ready'),
            'fallback': cond.get('Fallback')}


def gpu_binding(pod):
    result = subprocess.run(BASE + ['exec', pod['metadata']['name'], '--', 'nvidia-smi',
            '--query-gpu=uuid', '--format=csv,noheader'], capture_output=True, text=True, timeout=25)
    ids = [s.strip() for s in result.stdout.splitlines() if s.startswith('GPU-')]
    if result.returncode or len(ids) != 1:
        raise AssertionError('Expected exactly one visible GPU per TP1 Pod')
    return {'pod': pod['metadata']['name'], 'url': 'http://' + pod['status']['podIP'] + ':30000', 'gpu_uuid': ids[0]}


def gateway():
    code = ('import json,os,urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); '
            'get=lambda p:json.load(o.open(urllib.request.Request("http://127.0.0.1:8080"+p,headers={"Authorization":"Bearer "+os.environ["GATEWAY_API_KEY"]}),timeout=5)); '
            'r=get("/readiness"); w=get("/workers"); '
            'print(json.dumps({"readiness":r,"workers":{"workers":[{"url":x["url"],"is_healthy":x["is_healthy"]} for x in w["workers"]]}}))')
    return read(['exec', 'deployment/sglang-gateway', '--', 'python3', '-c', code])


def host_gpus(a):
    result = subprocess.run(['ssh', '-i', str(a.ssh_key.expanduser()),
        '-p',str(a.ssh_port),'-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        a.ssh_user+'@'+a.host, 'nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader'],
        capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError('Read-only host GPU process check failed')
    return sorted(set(line.strip() for line in result.stdout.splitlines() if line.startswith('GPU-')))


def record_counter_samples(baselines, maxima, values):
    for url, value in values.items():
        count = value['requests_total']
        # A new engine may already have startup/internal requests in its counter.
        baselines.setdefault(url, count)
        maxima[url] = max(maxima.get(url, count), count)


def main():
    parser = argparse.ArgumentParser(description='Bounded real GPU 1->2->1 acceptance; sends inference load through Gateway')
    add_target_arguments(parser)
    parser.add_argument('--run-load',action='store_true',help='Send up to256 requests, 8 closed-loop clients, 2048 output tokens each')
    parser.add_argument('--ssh-key',type=Path,default=Path.home()/'.ssh/sglang_lab_ed25519')
    parser.add_argument('--ssh-user',default='ubuntu')
    parser.add_argument('--ssh-port',type=int,default=22)
    a = parser.parse_args()
    if not a.run_load: parser.error('Pass --run-load for bounded GPU load')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*',a.ssh_user) or not 0<a.ssh_port<65536: parser.error('Invalid SSH user or port')
    global BASE,LAB
    target=configure_target(a);BASE=target.base;LAB=target.evidence
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', a.host):
        parser.error('Use the explicit current IPv4 address or DNS name')
    initial_pods = pods()
    assert len(initial_pods) == 1, 'Expected exactly one Ready Pod before load'
    first = gpu_binding(initial_pods[0])
    active = host_gpus(a)
    assert active == [first['gpu_uuid']], 'Expected only the first engine GPU active on the dedicated host'
    initial = state()
    assert initial['scaler_ready'] == 'True' and initial['fallback'] == 'False', initial
    assert all(initial[k] == 1 for k in ['hpa_desired', 'deployment_desired', 'deployment_current', 'deployment_ready']), initial
    current_gateway = gateway()
    VALIDATE(current_gateway['readiness'], current_gateway['workers'], [first['url']])
    output = LAB / ('real-scaling-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8] + '.jsonl')
    started = time.monotonic()
    events = queue.Queue()
    child = None
    with output.open('x') as stream:
        def emit(event):
            row = {**event, 'observer_elapsed_s': round(time.monotonic()-started, 2)}
            line = json.dumps(row)
            print(line, flush=True)
            stream.write(line + '\n')
            stream.flush()
        emit({'kind': 'initial', **initial, 'binding': first, 'evidence': str(output)})
        child = subprocess.Popen(BASE + ['exec', '-i', 'deployment/sglang-gateway', '--', 'python3', '-', first['url']],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        def reader():
            for line in child.stdout:
                try:
                    events.put(json.loads(line))
                except json.JSONDecodeError:
                    # Do not dump arbitrary remote exception text/headers to evidence.
                    events.put({'kind': 'remote_diagnostic', 'message': 'Non-JSON output; remote check may have failed'})
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        child.stdin.write((PAYLOADS/'real_gpu_load.py').read_text())
        child.stdin.close()
        up = fallback_seen = False
        bindings = {}
        baselines = {}
        maxima = {}
        done = None
        last = None
        try:
            while time.monotonic()-started < 900:
                while True:
                    try: event = events.get_nowait()
                    except queue.Empty: break
                    emit(event)
                    if event.get('kind') == 'baseline_counters':
                        baselines = {url: value['requests_total'] for url,value in event['values'].items()}
                    if event.get('kind') == 'backend_counters':
                        record_counter_samples(baselines, maxima, event['values'])
                    if event.get('kind') == 'load_done': done = event
                now = state()
                if now != last:
                    emit({'kind': 'controller', **now});last = now
                fallback_seen |= now['fallback'] == 'True'
                up |= now['hpa_desired'] == 2 and now['deployment_desired'] == 2
                ready = pods()
                if len(ready) == 2 and not bindings:
                    observed = [gpu_binding(p) for p in ready]
                    assert len({x['gpu_uuid'] for x in observed}) == 2, 'Both Pods bound to the same GPU'
                    bindings = {x['url']: x for x in observed}
                    emit({'kind': 'two_gpu_bindings', 'workers': observed})
                if child.poll() is not None and done is None and events.empty():
                    thread.join(timeout=1)
                    if events.empty(): raise RuntimeError('Load exited without summary; inspect evidence')
                down = done and child.poll() is not None and up and bindings and all(now[k] == 1 for k in
                       ['hpa_desired', 'deployment_desired', 'deployment_current', 'deployment_ready'])
                if down and len(ready) == 1:
                    # Wait for terminating Pods to disappear as well as GPU processes.
                    if len(read(['get', 'pods', '-l', 'app=sglang-worker', '-o', 'json'])['items']) != 1:
                        time.sleep(5);continue
                    assert child.returncode == 0 and done['failed'] == 0 and done['success'] > 0, 'Load failed'
                    deltas = {url: maxima.get(url, 0)-baselines.get(url, 0) for url in bindings}
                    assert all(x > 0 for x in deltas.values()), 'No observed request completions on both engines'
                    assert not fallback_seen, 'Fallback occurred; not accepted as load-only scaling'
                    survivor = gpu_binding(ready[0])
                    snapshot = gateway()
                    try: VALIDATE(snapshot['readiness'], snapshot['workers'], [survivor['url']])
                    except AssertionError:
                        time.sleep(5);continue
                    active = host_gpus(a)
                    emit({'kind': 'post_scale_down', 'survivor': survivor, 'active_gpu_uuids': active})
                    if active != [survivor['gpu_uuid']]:
                        time.sleep(5);continue
                    emit({'kind': 'PASS', 'hpa_scale_up': True, 'two_distinct_gpu_pods': True,
                          'backend_request_delta_lower_bound': deltas, 'scale_down_to_one': True,
                          'second_gpu_process_released': True, 'success': done['success'], 'failed': 0,
                          'scope': 'single-node TP1 replica elasticity; idle shrink, not in-flight drain/HA/capacity proof',
                          'evidence': str(output)})
                    return
                time.sleep(5)
            raise TimeoutError('900-second observation budget exceeded; preserve evidence and inspect')
        finally:
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill();child.wait()


if __name__ == '__main__':
    run_main(main)
