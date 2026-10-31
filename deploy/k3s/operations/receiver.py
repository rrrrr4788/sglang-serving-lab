"""Private lab webhook sink: stores bounded, filtered Alertmanager events in memory."""
import collections
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

LOCK = threading.Lock()
EVENTS = collections.deque(maxlen=128)
SEQUENCE = 0


def store_payload(payload):
    global SEQUENCE
    status = payload.get('status')
    alerts = payload.get('alerts')
    if status not in ('firing', 'resolved') or not isinstance(alerts, list) or len(alerts) > 16:
        raise ValueError('Unsupported alert envelope')
    selected = []
    for alert in alerts:
        labels = alert.get('labels', {})
        annotations = alert.get('annotations', {})
        selected.append({'status': alert.get('status'),
            'labels': {k: str(labels[k])[:256] for k in ['alertname', 'namespace', 'severity'] if k in labels},
            'annotations': {k: str(annotations[k])[:512] for k in ['summary', 'description', 'runbook_url'] if k in annotations},
            'startsAt': str(alert.get('startsAt', ''))[:64], 'endsAt': str(alert.get('endsAt', ''))[:64]})
    with LOCK:
        SEQUENCE += 1
        EVENTS.append({'seq': SEQUENCE, 'received_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'status': status, 'alerts': selected})
        return SEQUENCE


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        # No raw request bodies, headers or credential-bearing URLs in logs.
        pass

    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, {'alive': True})
        elif self.path == '/events':
            with LOCK:
                data = {'last_seq': SEQUENCE, 'events': list(EVENTS)}
            self.reply(200, data)
        else:
            self.reply(404, {})

    def do_POST(self):
        if self.path != '/alerts':
            self.reply(404, {});return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                self.reply(413, {});return
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Invalid envelope')
            seq = store_payload(payload)
        except (ValueError, TypeError, AttributeError, KeyError):
            self.reply(400, {});return
        self.reply(202, {'accepted': True, 'seq': seq})


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
