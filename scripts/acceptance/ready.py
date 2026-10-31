import argparse
import subprocess
from common import add_target_arguments, configure_target, PAYLOADS, run_main


def main():
    p=argparse.ArgumentParser(description='Cloud preflight (one 16-token request) or read-only operations snapshot')
    add_target_arguments(p)
    p.add_argument('--snapshot-only',action='store_true',help='Read-only alert/Gateway state; no inference')
    p.add_argument('--run-inference',action='store_true',help='Send one bounded preflight generation through the internal Gateway')
    a=p.parse_args()
    if a.snapshot_only == a.run_inference: p.error('Choose exactly one of --snapshot-only or --run-inference')
    target=configure_target(a)
    payload='operations_snapshot.py' if a.snapshot_only else 'cloud_ready.py'
    deployment='sglang-gateway' if a.snapshot_only else 'sglang-worker'
    result=subprocess.run(target.base+['exec','-i','deployment/'+deployment,'--','python3','-'],
        input=(PAYLOADS/payload).read_text(),capture_output=True,text=True,timeout=180)
    if result.returncode: raise RuntimeError('Remote acceptance failed; private output withheld')
    print(result.stdout,end='')


if __name__=='__main__': run_main(main)
