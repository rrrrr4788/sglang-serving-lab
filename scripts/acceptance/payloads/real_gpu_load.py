import collections
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
import uuid


def metric_sum(text, name):
    values = []
    pattern = re.compile(r'^' + re.escape(name) + r'(?:\{([^\n]*)\})?\s+([-+\deE.]+)(?:\s+\d+)?$')
    for line in text.splitlines():
        match = pattern.match(line)
        if match and (not match[1] or 'tp_rank=' not in match[1] or 'tp_rank="0"' in match[1]):
            values.append(float(match[2]))
    if not values:
        raise ValueError('Required engine metric missing: ' + name)
    return sum(values)


def main():
    key = os.environ['GATEWAY_API_KEY']
    base = 'http://127.0.0.1:8080'
    expected = sys.argv[1]
    lock = threading.Lock()
    rows = []
    next_request = 0
    started = time.monotonic()
    deadline = started + 300

    def emit(event):
        with lock:
            print(json.dumps({'load_elapsed_s': round(time.monotonic()-started, 2), **event}), flush=True)

    def request(url, body=None, timeout=10, raw=False):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
              headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with opener.open(req, timeout=timeout) as response:
            data = response.read()
            return response.status, data.decode() if raw else json.loads(data)

    def snapshot():
        _, ready = request(base + '/readiness')
        _, workers = request(base + '/workers')
        healthy = sorted(w['url'].rstrip('/') for w in workers['workers'] if w.get('is_healthy') is True)
        assert ready['healthy_workers'] == len(healthy)
        values = {}
        for url in healthy:
            _, metrics = request(url + '/metrics', raw=True)
            values[url] = {'requests_total': metric_sum(metrics, 'sglang:num_requests_total'),
                           'running': metric_sum(metrics, 'sglang:num_running_reqs'),
                           'queued': metric_sum(metrics, 'sglang:num_queue_reqs')}
        return healthy, values

    healthy, before = snapshot()
    assert healthy == [expected], 'Expected only the current Ready backend before load'
    emit({'kind': 'baseline_counters', 'values': before})
    emit({'kind': 'load_start', 'concurrency': 8, 'arrival': 'bounded closed-loop',
          'admission_duration_s': 300, 'request_limit': 256, 'request_timeout_s': 90,
          'input_tokens': 64, 'output_tokens': 2048, 'ignore_eos': True,
          'temperature': 0, 'cache': 'retained', 'stream': False,
          'scope': 'autoscaling acceptance, not representative capacity/TTFT evidence'})

    def client(slot):
        nonlocal next_request
        while time.monotonic() < deadline:
            with lock:
                if next_request >= 256:
                    return
                sequence = next_request
                next_request += 1
            row = {'request': sequence, 'status': None, 'ok': False}
            tic = time.monotonic()
            try:
                status, result = request(base + '/generate', {
                    'rid': 'gpu-scale-' + uuid.uuid4().hex, 'input_ids': [1000] * 64,
                    'sampling_params': {'max_new_tokens': 2048, 'temperature': 0, 'ignore_eos': True},
                    'stream': False}, timeout=90)
                row['status'] = status
                info = result.get('meta_info', {})
                assert status == 200 and info.get('completion_tokens') == 2048 and info.get('prompt_tokens') == 64
                assert info.get('finish_reason') is not None
                row.update(ok=True, output_tokens=2048, e2e_s=round(time.monotonic()-tic, 3))
            except urllib.error.HTTPError as error:
                row.update(status=error.code, error='HTTPError')
                error.close()
            except Exception as error:
                row['error'] = type(error).__name__
            with lock:
                rows.append(row)
                errors = sum(not x['ok'] for x in rows)
            if not row['ok']:
                emit({'kind': 'request_error', **row})
                if errors >= 5:
                    return
                time.sleep(1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(client, slot) for slot in range(8)]
        while not all(job.done() for job in jobs):
            try:
                healthy, counters = snapshot()
                emit({'kind': 'backend_counters', 'healthy_urls': healthy, 'values': counters})
            except Exception as error:
                emit({'kind': 'snapshot_error', 'error': type(error).__name__})
            time.sleep(5)
        for job in jobs:
            job.result()
    # One last sample before HPA's downscale window removes a backend.
    healthy, counters = snapshot()
    emit({'kind': 'backend_counters', 'healthy_urls': healthy, 'values': counters})
    elapsed = time.monotonic() - started
    success = [row for row in rows if row['ok']]
    emit({'kind': 'load_done', 'success': len(success), 'failed': len(rows)-len(success),
          'status_counts': dict(collections.Counter(str(row['status']) for row in rows)),
          'output_tokens': sum(x['output_tokens'] for x in success),
          'mean_e2e_s': round(sum(x['e2e_s'] for x in success)/len(success), 3) if success else None,
          'elapsed_s': round(elapsed, 2)})
    if not success or len(success) != len(rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
