#!/usr/bin/env python3
"""Check API authentication and one small inference request. Uses host environment."""
import json
import os
import urllib.error
import urllib.request

base = 'http://127.0.0.1:' + os.environ.get('SGLANG_PORT', '30000')
key = os.environ.get('SGLANG_API_KEY')
if not key:
    raise SystemExit('Export SGLANG_API_KEY from your private .env first.')

def request(path, auth=None, body=None):
    headers = {'Content-Type': 'application/json'}
    if auth is not None:
        headers['Authorization'] = 'Bearer ' + auth
    req = urllib.request.Request(base + path, headers=headers,
          data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()

for credential in [None, key + '-invalid']:
    status, _ = request('/v1/models', credential)
    if status != 401:
        raise SystemExit(f'Authentication check failed: expected 401, received {status}')
status, data = request('/v1/models', key)
if status != 200:
    raise SystemExit(f'Authenticated model listing failed: HTTP {status}')
model = json.loads(data)['data'][0]['id']
status, data = request('/v1/chat/completions', key, {
    'model': model, 'messages': [{'role': 'user', 'content': 'Say hello.'}],
    'max_tokens': 8, 'temperature': 0, 'stream': False})
if status != 200 or not json.loads(data).get('choices'):
    raise SystemExit(f'Inference check failed: HTTP {status}')
print('PASS: missing/wrong credentials rejected; authenticated model listing and inference succeeded.')
