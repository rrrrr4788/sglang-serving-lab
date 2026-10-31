"""Full maintenance-control replay; every cluster/network/generation operation is replaced."""
import contextlib
import copy
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

PUBLIC=Path(__file__).resolve().parents[1]/'scripts/acceptance'
sys.path.insert(0,str(PUBLIC))
MODULE=runpy.run_path(str(PUBLIC/'operations.py'))
G=MODULE['main'].__globals__
TEMPLATE={'metadata':{'labels':{'app':'sglang-worker'}},'spec':{'terminationGracePeriodSeconds':180,'containers':[{'name':'engine','image':'fixed-fixture-image','args':['--context-length','4096','--api-key','$(SGLANG_API_KEY)']}]}}
ORIGINAL={'metadata':{'resourceVersion':'v1','annotations':{'deployment.kubernetes.io/revision':'1'}},'spec':{'replicas':1,'template':TEMPLATE},'status':{'readyReplicas':1}}
OLD={'metadata':{'name':'old-pod','uid':'old-uid'},'status':{'podIP':'10.42.0.9'}}
NEW={'metadata':{'name':'new-pod','uid':'new-uid'},'status':{'podIP':'10.42.0.10'}}


def replay(case):
    state={'deployment':copy.deepcopy(ORIGINAL),'paused':False,'owner':None,'fault':False,'rollback':False,'undos':0,'clock':0,'client':False}
    def read(args):
        target=args[1]
        if target=='deployment':
            if case=='foreign_owner' and state['fault']:
                state['deployment']['spec']['template']['metadata']['annotations'][G['OWNER']]='other-operator'
            return copy.deepcopy(state['deployment'])
        if target=='node': return {'status':{'addresses':[{'address':'192.0.2.10'}]}}
        if target=='scaledobject':
            annotations={}
            if state['paused']: annotations={G['PAUSE']:'1',G['OWNER']:state['owner']}
            return {'metadata':{'annotations':annotations},'status':{'conditions':[{'type':'Ready','status':'True'},{'type':'Fallback','status':'False'},{'type':'Paused','status':'True' if state['paused'] else 'False'}]}}
        if target=='pods': return {'items':[{'metadata':{'uid':'bad-uid'},'status':{'containerStatuses':[{'state':{'waiting':{'reason':'CrashLoopBackOff'}}}]}}]}
        raise AssertionError(args)
    def command(args,data=None,timeout=25):
        if args[0]=='annotate':
            if G['PAUSE']+'=1' in args:
                state['paused']=True;state['owner']=next(x.split('=',1)[1] for x in args if x.startswith(G['OWNER']+'='))
                if case=='pause_ack_lost': raise RuntimeError('simulated lost pause acknowledgement')
            else: state['paused']=False;state['owner']=None
        elif args[0]=='patch':
            operations=json.loads(args[-1]);assert operations[0]['op']=='test'
            state['deployment']['spec']['template']['spec']['containers'][0]['args'].append(G['BAD_ARG'])
            state['deployment']['spec']['template']['metadata']['annotations']=operations[-1]['value']
            state['deployment']['metadata']['annotations']['deployment.kubernetes.io/revision']='2'
            state['fault']=True
            if case=='patch_ack_lost': raise RuntimeError('simulated lost patch acknowledgement')
        elif args[:2]==['rollout','undo']:
            assert args[-1]=='--to-revision=1'
            state['undos']+=1;state['deployment']['spec']['template']=copy.deepcopy(TEMPLATE)
            state['deployment']['metadata']['annotations']['deployment.kubernetes.io/revision']='3'
            state['fault']=False;state['rollback']=True
        elif args[:2]==['rollout','status']: pass
        else: raise AssertionError(args)
        return ''
    def event(seq,status): return {'seq':seq,'status':status,'alerts':[{'status':status,'labels':{'alertname':'SGLangNoReadyWorker','namespace':'sglang-platform'}}]}
    def snapshot(old=None):
        events=[event(1,'firing')] if state['fault'] else ([event(1,'firing'),event(2,'resolved')] if state['rollback'] else [])
        healthy=[] if state['fault'] else ['http://10.42.0.10:30000' if state['rollback'] else 'http://10.42.0.9:30000']
        value={'gateway_status':503 if state['fault'] else 200,'healthy_urls':healthy,'rule_state':'firing' if state['fault'] else 'inactive','rule_health':'ok','alertmanager_status':200,'receiver':{'last_seq':events[-1]['seq'] if events else 0,'events':events}}
        if old: value['old']={'health':503 if state['fault'] else 200,'running':1}
        return value
    class Request:
        def __init__(self,key):
            self.result={'ok':True,'status':200,'tokens':3500,'done_marker':True}
            self.admitted=SimpleNamespace(wait=lambda timeout:True)
            self.done=SimpleNamespace(is_set=lambda:state['fault'] or state['rollback'])
            self.thread=SimpleNamespace(start=lambda:state.update(client=True))
        def close(self): pass
    def public(key,body): return (503,None) if state['fault'] else (200,{'meta_info':{'completion_tokens':16}})
    def clock(): state['clock']+=1;return state['clock']
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);(tmp/'.private').mkdir();(tmp/'.private/cloud-engine.key').write_text('offline-fixture');logs=tmp/'logs';logs.mkdir()
        replacements={'configure_target':lambda a,public=False:SimpleNamespace(base=[],evidence=logs,key_file=tmp/'.private/cloud-engine.key',base_url='https://example.invalid'),'private_key':lambda _: 'offline-fixture','read':read,'command':command,'snapshot':snapshot,'ready_pods':lambda:[NEW if state['rollback'] else OLD],'InflightRequest':Request,'public_call':public,'time':SimpleNamespace(monotonic=clock,sleep=lambda _:None)}
        with patch.dict(G,replacements),patch.object(sys,'argv',['operations','--host','192.0.2.10','--base-url','https://example.invalid','--run-maintenance']),contextlib.redirect_stdout(io.StringIO()):
            if case=='success': MODULE['main']()
            else:
                try: MODULE['main']()
                except SystemExit as error: assert error.code==1
                else: raise AssertionError('Failure incorrectly passed: '+case)
        events=[json.loads(x) for x in next(logs.glob('*.jsonl')).read_text().splitlines()]
        assert events[-1]['kind']==('PASS' if case=='success' else 'FAIL')
    if case=='foreign_owner':
        assert state['undos']==0 and state['paused'], 'Must not overwrite another operator or resume an unrecovered service'
    else:
        assert not state['paused'] and state['deployment']['spec']['template']==TEMPLATE
        assert state['undos']==(0 if case=='pause_ack_lost' else 1)
    print('PASS offline maintenance replay:',case)


import unittest


class MaintenanceReplayTests(unittest.TestCase):
    def test_success(self): replay('success')
    def test_pause_ack_lost(self): replay('pause_ack_lost')
    def test_patch_ack_lost(self): replay('patch_ack_lost')
    def test_foreign_owner(self): replay('foreign_owner')


if __name__=='__main__': unittest.main()
