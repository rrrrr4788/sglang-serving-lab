#!/usr/bin/env python3
"""Run synthetic benchmarks with the client bundled in the pinned server image."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('suite', choices=['length', 'prefix', 'concurrency'])
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out = root / 'results' / 'raw' / stamp
out.mkdir(parents=True)
common = ['--backend', 'sglang', '--host', '127.0.0.1', '--port', '30000',
          '--model', 'Qwen/Qwen3-0.6B', '--seed', '42', '--disable-ignore-eos']
random = ['--dataset-name', 'random', '--num-prompts', '100', '--random-range-ratio', '0']
if args.suite == 'length':
    cases = [(f'{a}_{b}', random + ['--max-concurrency', '8', '--random-input-len', str(a),
              '--random-output-len', str(b)]) for a,b in [(128,128),(1024,128),(128,512),(1024,512)]]
elif args.suite == 'concurrency':
    cases = [(f'c{c}', random + ['--max-concurrency', str(c), '--random-input-len', '128',
              '--random-output-len', '128']) for c in [1,2,4,8,16]]
else:
    cases = [(name, ['--dataset-name', 'generated-shared-prefix', '--num-prompts', '64',
              '--max-concurrency', '8', '--gsp-num-groups', str(groups),
              '--gsp-prompts-per-group', str(per_group), '--gsp-system-prompt-len', '512',
              '--gsp-question-len', '64', '--gsp-output-len', '64', '--gsp-range-ratio', '1',
              '--flush-cache']) for name,groups,per_group in [('unique',64,1),('shared',1,64)]]
# Credentials remain inside the container environment, away from command arguments/logs.
# Cache flush uses the API key; no separate admin key is configured in this lab.
base = ['docker', 'compose', 'exec', '-T', 'sglang', 'sh', '-ec',
        'export OPENAI_API_KEY="$SGLANG_API_KEY"; exec python3 -m sglang.bench_serving "$@"', 'bench']
metadata = {'started_at_utc': stamp, 'suite': args.suite, 'cases': [],
            'notes': 'Synthetic workload. EOS is allowed; requested lengths are not exact generated token counts.'}
for name,flags in cases:
    print(f'Running {name}; output: {out / (name + ".txt")}', flush=True)
    with (out / (name + '.txt')).open('w', encoding='utf-8') as log:
        result = subprocess.run(base + common + flags, cwd=root, stdout=log, stderr=subprocess.STDOUT, text=True)
    metadata['cases'].append({'name': name, 'arguments': common + flags, 'exit_code': result.returncode})
    (out / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    if result.returncode:
        raise SystemExit(f'Benchmark failed; inspect {out / (name + ".txt")}')
print('Finished. Review logs before publishing any results.')
