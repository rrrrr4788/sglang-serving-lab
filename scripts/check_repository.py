#!/usr/bin/env python3
"""Offline documentation/public-tool checks; no cluster, network or credential access."""
import ast
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def check():
    errors=[]
    manifest=json.loads((ROOT/'docs/languages.json').read_text())
    seen=set()
    fences=chr(96)*3
    def shell_blocks(text):
        return re.findall(fences+r'(?:bash|sh)\n(.*?)'+fences,text,re.S)
    for english,chinese in manifest['pairs']:
        paths=[ROOT/english,ROOT/chinese]
        if len(set([english,chinese]))!=2 or seen.intersection([english,chinese]):
            errors.append('Duplicate language pair: '+english)
        seen.update([english,chinese])
        if not all(p.is_file() for p in paths):
            errors.append('Missing counterpart: '+english);continue
        en,zh=[p.read_text() for p in paths]
        if '('+paths[1].name+')' not in en or '('+paths[0].name+')' not in zh:
            errors.append('Missing reciprocal language navigation: '+english)
        if shell_blocks(en)!=shell_blocks(zh):
            errors.append('Shell commands diverge: '+english)
    for p in [ROOT/'README.md',ROOT/'README.zh-CN.md',*sorted((ROOT/'docs').rglob('*.md'))]:
        text=p.read_text()
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if '://' in link or link.startswith(('#','mailto:')):continue
            target=link.split('#')[0]
            if target and not (p.parent/target).exists():
                errors.append('Broken link: '+str(p.relative_to(ROOT))+' -> '+target)
        if any(line.rstrip()!=line for line in text.splitlines()):
            errors.append('Trailing whitespace: '+str(p.relative_to(ROOT)))
    for p in (ROOT/'scripts/acceptance').rglob('*.py'):
        text=p.read_text();ast.parse(text)
        if '.private/labs/' in text or '64.247.196.' in text:
            errors.append('Private source/old host dependency: '+str(p.relative_to(ROOT)))
    if 'inference.example.invalid' not in (ROOT/'deploy/k3s/inference-ingress.yaml').read_text():
        errors.append('Ingress must retain a neutral template hostname')
    for error in errors:print('FAIL:',error)
    if errors:raise SystemExit(1)
    print('PASS: '+str(len(manifest['pairs']))+' bilingual pairs, identical shell blocks, local links and public tool independence.')


if __name__=='__main__':check()
