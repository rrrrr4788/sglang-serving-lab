#!/usr/bin/env python3
"""Validate checked-in artifacts without starting services or reading private .env."""
import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess

root = Path(__file__).resolve().parents[1]
for file in [root / 'benchmarks/run.py', root / 'scripts/smoke.py']:
    py_compile.compile(str(file), doraise=True)
for file in root.rglob('*.json'):
    if not {'.git', '.private', '.venv', '__pycache__', 'raw'}.intersection(file.relative_to(root).parts):
        json.loads(file.read_text(encoding='utf-8'))
manifest = json.loads((root / 'results/legacy/manifest.json').read_text())
for entry in manifest['files']:
    data = (root / entry['imported_file']).read_bytes()
    if hashlib.sha256(data).hexdigest() != entry['imported_sha256']:
        raise SystemExit('Imported evidence hash mismatch: ' + entry['imported_file'])
env = os.environ.copy()
env.update(SGLANG_API_KEY='validation-only', GRAFANA_ADMIN_PASSWORD='validation-only')
# Explicit example file prevents loading the user's real secrets during validation.
result = subprocess.run(['docker', 'compose', '--env-file', '.env.example', 'config', '--format', 'json'],
                        cwd=root, env=env, capture_output=True, text=True)
if result.returncode:
    raise SystemExit('Compose validation failed: ' + result.stderr)
config = json.loads(result.stdout)
for service in config['services'].values():
    for port in service.get('ports', []):
        if port['host_ip'] != '127.0.0.1':
            raise SystemExit('Published port must bind to loopback')
if '@sha256:' not in config['services']['sglang']['image']:
    raise SystemExit('SGLang image must be digest pinned')
print('PASS: Python syntax, JSON, historical evidence hashes, Compose and loopback ports.')
