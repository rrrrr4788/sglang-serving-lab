import json
import os
import re
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def metric(text, name, required=True):
    values = []
    pattern = re.compile(r'^' + re.escape(name) + r'(?:\{([^\n]*)\})?\s+([-+\deE.]+)(?:\s+\d+)?$')
    for line in text.splitlines():
        match = pattern.match(line)
        if match and (not match[1] or 'tp_rank=' not in match[1] or 'tp_rank="0"' in match[1]):
            values.append(float(match[2]))
    if not values:
        if required:
            raise ValueError('Required engine metric absent: ' + name)
        return None
    return sum(values)


def main():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    key = os.environ['GATEWAY_API_KEY']
    def request(url):
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key})
        with opener.open(req, timeout=5) as response:
            return response.read()
    workers = json.loads(request('http://127.0.0.1:8080/workers'))['workers']
    healthy = [x['url'].rstrip('/') for x in workers if x.get('is_healthy') is True]
    assert len(healthy) == 1, 'Expected one healthy real worker during this single-client check'
    text = request(healthy[0] + '/metrics').decode()
    print(json.dumps({'worker_url': healthy[0],
        'running': metric(text, 'sglang:num_running_reqs'),
        'queued': metric(text, 'sglang:num_queue_reqs'),
        'generated': metric(text, 'sglang:generation_tokens_total'),
        'completed': metric(text, 'sglang:num_requests_total'),
        'aborted': metric(text, 'sglang:num_aborted_requests_total', required=False)}), flush=True)


if __name__ == '__main__':
    main()
