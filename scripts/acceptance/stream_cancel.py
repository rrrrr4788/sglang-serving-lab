import datetime
import json
from pathlib import Path
import signal
import ssl
import subprocess
import time
import urllib.request
import uuid

from common import add_target_arguments, configure_target, private_key, PAYLOADS, sse_events, NoRedirect, run_main

BASE=[]
LAB=None
PUBLIC_BASE=None


def abort_observed(before, after):
    # A label series may be lazily created; preserve an absent baseline as None.
    return after is not None and (after > before if before is not None else after > 0)


def snapshot():
    result = subprocess.run(BASE + ['exec', '-i', 'deployment/sglang-gateway', '--', 'python3', '-'],
          input=(PAYLOADS / 'engine_snapshot.py').read_text(), capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Read-only engine snapshot failed; raw output withheld')
    return json.loads(result.stdout)


def main():
    import argparse
    p=argparse.ArgumentParser(description='One complete128-token SSE and one3500-token early disconnect; no cache flush')
    add_target_arguments(p,public=True)
    p.add_argument('--run-inference',action='store_true')
    a=p.parse_args()
    if not a.run_inference: p.error('Pass --run-inference for two bounded requests')
    global BASE,LAB,PUBLIC_BASE
    target=configure_target(a,public=True);BASE=target.base;LAB=target.evidence;PUBLIC_BASE=target.base_url
    output = LAB / ('stream-cancel-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8] + '.jsonl')
    started = time.monotonic()
    key = private_key(target.key_file)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    baseline = snapshot()
    assert baseline['running'] == baseline['queued'] == 0, 'Run without other generation traffic'
    def expired(signum, frame):
        raise TimeoutError('150-second total stream/cancel budget exceeded')
    old_handler = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 150)
    with output.open('x') as log:
        def emit(event):
            line = json.dumps({'elapsed_s': round(time.monotonic()-started, 3), **event})
            print(line, flush=True);log.write(line + '\n');log.flush()
        def checked_snapshot():
            value = snapshot()
            assert value['worker_url'] == baseline['worker_url'], 'Worker changed during test'
            assert value['generated'] >= baseline['generated'], 'Metric reset during test'
            emit({'kind': 'engine_snapshot', **value})
            return value
        def open_stream(limit, rid):
            req = urllib.request.Request(PUBLIC_BASE + '/generate',
                data=json.dumps({'rid': rid, 'input_ids': [1000] * 64, 'stream': True,
                      'sampling_params': {'max_new_tokens': limit, 'ignore_eos': True, 'temperature': 0}}).encode(),
                headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
            response = opener.open(req, timeout=20)
            assert response.status == 200
            assert response.headers.get_content_type() == 'text/event-stream'
            return response
        def validate_event(event, rid, previous):
            meta = event.get('meta_info', {})
            assert meta.get('id') == rid, 'SSE request ID mismatch'
            count = int(meta.get('completion_tokens', 0))
            assert count >= previous, 'Cumulative output token count decreased'
            return meta, count
        try:
            emit({'kind': 'initial', 'metric': baseline, 'evidence': str(output)})
            rid = 'stream-complete-' + uuid.uuid4().hex
            counts = [];finished = done = False
            tic = time.monotonic();first = None
            with open_stream(128, rid) as response:
                for event in sse_events(response):
                    if event is None: done = True;break
                    meta, count = validate_event(event, rid, counts[-1] if counts else 0)
                    if count > 0 and first is None: first = time.monotonic()
                    counts.append(count)
                    finished |= meta.get('finish_reason') is not None
            assert done and finished and counts[-1] == 128 and len(set(counts)) >= 2
            emit({'kind': 'stream_complete', 'status': 200, 'output_tokens': 128,
                  'events': len(counts), 'ttft_ms': round((first-tic)*1000, 3),
                  'e2e_s': round(time.monotonic()-tic, 3), 'done_marker': done})
            deadline = time.monotonic() + 15
            while True:
                before = checked_snapshot()
                if before['running'] == before['queued'] == 0 and before['generated']-baseline['generated'] == 128:
                    break
                if time.monotonic() > deadline: raise TimeoutError('Normal stream completion metric did not settle')
                time.sleep(0.25)
            rid = 'stream-cancel-' + uuid.uuid4().hex
            response = open_stream(3500, rid)
            observed_tokens = 0
            try:
                for event in sse_events(response):
                    assert event is not None, 'Cancellation stream ended before early close'
                    meta, observed_tokens = validate_event(event, rid, observed_tokens)
                    assert meta.get('finish_reason') is None, 'Already finished before cancellation'
                    if observed_tokens >= 32:
                        break
                assert 0 < observed_tokens < 3500
                active = checked_snapshot()
                assert active['running'] == 1 and active['queued'] == 0, 'No active request immediately before disconnect; cancellation not proven'
                emit({'kind': 'client_disconnect', 'received_tokens': observed_tokens,
                      'requested_output_tokens': 3500, 'active_before_close': active['running']})
            finally:
                response.close()
            closed = time.monotonic()
            deadline = closed + 30
            consecutive = 0
            while time.monotonic() < deadline:
                after = checked_snapshot()
                idle = after['running'] == after['queued'] == 0
                abort = abort_observed(before['aborted'], after['aborted'])
                generation_delta = after['generated']-before['generated']
                # Two idle snapshots plus abort signal, and no full-length completion.
                consecutive = consecutive + 1 if idle and abort and 0 <= generation_delta < 3500 else 0
                if consecutive >= 2:
                    emit({'kind': 'PASS', 'stream_complete': True, 'client_closed_early': True,
                          'abort_before': before['aborted'], 'abort_after': after['aborted'],
                          'cancel_request_generated_tokens': generation_delta,
                          'active_requests_cleared': True, 'observed_clearance_s': round(time.monotonic()-closed, 3),
                          'scope': 'one normal SSE and one cancel through HTTPS; active request reclaimed, not VRAM pool release',
                          'evidence': str(output)})
                    return
                time.sleep(0.5)
            raise TimeoutError('No abort-counter increase plus sustained idle state within30s')
        except Exception as error:
            emit({'kind': 'FAIL', 'error': type(error).__name__, 'evidence': str(output)})
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)


if __name__ == '__main__':
    run_main(main)
