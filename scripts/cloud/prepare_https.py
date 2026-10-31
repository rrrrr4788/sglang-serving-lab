#!/usr/bin/env python3
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]


def render(host,hostname,output,email):
    ipaddress.IPv4Address(host)
    if not re.fullmatch(r'(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',hostname):
        raise ValueError('Invalid lowercase DNS hostname')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in hostname.split('.')):
        raise ValueError('Invalid DNS label')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise ValueError('Invalid ACME contact email')
    output=output.resolve()
    if not output.is_relative_to((ROOT/'.private').resolve()): raise ValueError('Render output must stay under .private')
    template=(ROOT/'deploy/k3s/inference-ingress.yaml').read_text()
    if template.count('inference.example.invalid')!=1: raise ValueError('Unexpected ingress template')
    os.umask(0o077)
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    paths=[output/'inference-ingress.yaml',output/'traefik-contact.json']
    if any(p.exists() for p in paths): raise FileExistsError('Choose a new output directory; existing render preserved')
    bodies=[template.replace('inference.example.invalid',hostname),
            json.dumps({'certificatesResolvers':{'le':{'acme':{'email':email}}}},indent=2)+'\n']
    for p,body in zip(paths,bodies):
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream: stream.write(body)
    return paths


def main():
    p=argparse.ArgumentParser(description='Local HTTPS render only: no network, deployment or certificate request')
    p.add_argument('--host',required=True,help='Current VM IPv4; no saved host')
    p.add_argument('--hostname',help='Defaults to an IP-encoded sslip.io name; DNS must be checked before installation')
    p.add_argument('--output-dir',type=Path,required=True,help='New directory under repository .private')
    p.add_argument('--contact-file',type=Path,help='Existing private JSON overlay; otherwise prompt locally without echo')
    a=p.parse_args()
    host=str(ipaddress.IPv4Address(a.host))
    hostname=a.hostname or 'sglang-'+host.replace('.','-')+'.sslip.io'
    if a.contact_file:
        email=json.loads(a.contact_file.read_text())['certificatesResolvers']['le']['acme']['email']
    else:
        email=getpass.getpass('ACME contact email (private; sent to CA on issuance): ').strip()
    render(host,hostname,a.output_dir,email)
    print('Local HTTPS files prepared in '+str(a.output_dir)+'. Contact not displayed; no network/deployment performed.')


if __name__=='__main__':
    try: main()
    except Exception as error: sys.exit('HTTPS preparation failed: '+type(error).__name__+'; existing files preserved; private details withheld.')
