import argparse
import datetime
import json
from pathlib import Path
import runpy
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

from common import add_target_arguments, configure_target, private_key, PAYLOADS, sse_events as SSE, NoRedirect as NO_REDIRECT, run_main

LAB=None
BASE=[]
PUBLIC_BASE=None
PAUSE='autoscaling.keda.sh/paused-replicas'
OWNER='sglang.lab/ops-run'
BAD_ARG='--lab-intentional-invalid-option'


def command(args,data=None,timeout=25):
    result=subprocess.run(BASE+args,input=data,capture_output=True,text=True,timeout=timeout)
    if result.returncode: raise RuntimeError('Kubernetes operation failed; raw output withheld (credentials may be present)')
    return result.stdout


def read(args): return json.loads(command(args))


def conditions(obj): return {x['type']:x['status'] for x in obj.get('status',{}).get('conditions',[])}


def ready_pods():
    return [p for p in read(['get','pods','-l','app=sglang-worker','-o','json'])['items'] if not p['metadata'].get('deletionTimestamp') and any(c.get('type')=='Ready' and c.get('status')=='True' for c in p.get('status',{}).get('conditions',[]))]


def snapshot(old=None):
    args=['exec','-i','deployment/sglang-gateway','--','python3','-']+([old] if old else [])
    return json.loads(command(args,(PAYLOADS/'operations_snapshot.py').read_text()))


def notification(snapshot,after_seq,status):
    return [e for e in snapshot['receiver']['events'] if e['seq']>after_seq and any(
        a.get('status')==status and a.get('labels',{}).get('alertname')=='SGLangNoReadyWorker' and a.get('labels',{}).get('namespace')=='sglang-platform' for a in e['alerts'])]


def public_call(key,body):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NO_REDIRECT(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req=urllib.request.Request(PUBLIC_BASE+'/generate',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with opener.open(req,timeout=30) as response: return response.status,json.load(response)
    except urllib.error.HTTPError as error:
        status=error.code;error.close();return status,None


class InflightRequest:
    def __init__(self,key):
        self.key=key;self.admitted=threading.Event();self.done=threading.Event();self.result=None;self.response=None
        self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        rid='drain-'+uuid.uuid4().hex
        count=0;finished=done=False
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NO_REDIRECT(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            req=urllib.request.Request(PUBLIC_BASE+'/generate',data=json.dumps({'rid':rid,'input_ids':[1000]*64,'stream':True,'sampling_params':{'max_new_tokens':3500,'ignore_eos':True,'temperature':0}}).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            with opener.open(req,timeout=30) as response:
                self.response=response
                assert response.status==200
                for event in SSE(response):
                    if event is None: done=True;break
                    info=event.get('meta_info',{});assert info.get('id')==rid
                    new=int(info.get('completion_tokens',0));assert new>=count;count=new
                    finished|=info.get('finish_reason') is not None
                    if count>=32: self.admitted.set()
            self.result={'ok':done and finished and count==3500,'status':200,'tokens':count,'done_marker':done}
        except Exception as error: self.result={'ok':False,'error':type(error).__name__,'tokens':count}
        finally: self.done.set()
    def close(self):
        if self.response is not None: self.response.close()


def wait(predicate,timeout,label,emit):
    deadline=time.monotonic()+timeout
    while True:
        result=predicate()
        if result: return result
        if time.monotonic()>deadline: raise TimeoutError(label)
        time.sleep(2)


def main():
    parser=argparse.ArgumentParser(description='Intentional invalid-config rollout: real drain, private firing/resolved delivery and rollback. Causes a temporary outage.')
    add_target_arguments(parser,public=True)
    parser.add_argument('--run-maintenance',action='store_true',help='Perform the described single-replica maintenance experiment')
    a=parser.parse_args()
    if not a.run_maintenance: parser.error('Read docs/operations.md, then pass --run-maintenance for the planned outage')
    global BASE,LAB,PUBLIC_BASE
    target=configure_target(a,public=True);BASE=target.base;LAB=target.evidence;PUBLIC_BASE=target.base_url
    key=private_key(target.key_file)
    original=read(['get','deployment','sglang-worker','-o','json'])
    assert original['spec'].get('replicas',1)==original.get('status',{}).get('readyReplicas',0)==1
    old_pods=ready_pods();assert len(old_pods)==1
    old_pod=old_pods[0];old_url='http://'+old_pod['status']['podIP']+':30000'
    template=original['spec']['template'];engine=next(c for c in template['spec']['containers'] if c['name']=='engine')
    assert BAD_ARG not in engine['args'] and template['spec']['terminationGracePeriodSeconds']>=180
    assert engine['args'][engine['args'].index('--context-length')+1]=='4096'
    revision=original['metadata']['annotations']['deployment.kubernetes.io/revision']
    scaler=read(['get','scaledobject','sglang-worker-load','-o','json'])
    assert conditions(scaler).get('Ready')=='True' and conditions(scaler).get('Fallback')=='False'
    annotations=scaler['metadata'].get('annotations',{})
    assert not any(k.startswith('autoscaling.keda.sh/paused') for k in annotations) and OWNER not in annotations, 'Already paused/owned; inspect ownership'
    before=snapshot();assert before['gateway_status']==200 and before['healthy_urls']==[old_url]
    assert before['rule_health']=='ok' and before['rule_state']=='inactive' and before['alertmanager_status']==200
    seq=before['receiver']['last_seq']
    token=uuid.uuid4().hex
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    evidence=LAB/('operations-'+stamp+'.jsonl');checkpoint=LAB/('recovery-'+stamp+'.json')
    checkpoint.write_text(json.dumps({'context':a.context,'kubeconfig':str(a.kubeconfig.resolve()),'host':a.host,'base_url':PUBLIC_BASE,'namespace':'sglang-platform','deployment':'sglang-worker','original_revision':revision,'owner_token':token,'old_pod_uid':old_pod['metadata']['uid']},indent=2)+'\n');checkpoint.chmod(0o600)
    started=time.monotonic();paused=faulted=released=recovered=False;request=None;failure=None;last=None
    with evidence.open('x') as log:
        def emit(event):
            line=json.dumps({'elapsed_s':round(time.monotonic()-started,2),**event});print(line,flush=True);log.write(line+'\n');log.flush()
        emit({'kind':'initial','original_revision':revision,'old_pod':old_pod['metadata']['name'],'old_pod_uid':old_pod['metadata']['uid'],'receiver_sequence':seq,'evidence':str(evidence),'recovery':str(checkpoint),'planned_outage':True,'release_type':'intentional invalid CLI configuration, image unchanged'})
        try:
            # Record possible mutation before sending it: lost acknowledgements still need cleanup.
            paused=True
            command(['annotate','scaledobject/sglang-worker-load',PAUSE+'=1',OWNER+'='+token,'--overwrite'])
            wait(lambda:conditions(read(['get','scaledobject','sglang-worker-load','-o','json'])).get('Paused')=='True',60,'KEDA did not pause',emit)
            emit({'kind':'autoscaling_paused','replicas':1})
            request=InflightRequest(key);request.thread.start()
            assert request.admitted.wait(20), 'No partial streamed response before maintenance'
            observed=snapshot(old_url)
            assert observed['old']['running']==1 and not request.done.is_set(), 'No in-flight request at rollout trigger'
            emit({'kind':'inflight_confirmed','health':observed['old']['health'],'running':observed['old']['running']})
            i=next(i for i,c in enumerate(template['spec']['containers']) if c['name']=='engine')
            mark={**template['metadata'].get('annotations',{}),OWNER:token}
            patch=[{'op':'test','path':'/metadata/resourceVersion','value':original['metadata']['resourceVersion']},
                   {'op':'add','path':f'/spec/template/spec/containers/{i}/args/-','value':BAD_ARG},
                   {'op':'add','path':'/spec/template/metadata/annotations','value':mark}]
            # Refresh only metadata.resourceVersion after the pause controller has reconciled.
            live=read(['get','deployment','sglang-worker','-o','json'])
            assert live['spec']['template']==template, 'Worker template changed concurrently'
            patch[0]['value']=live['metadata']['resourceVersion']
            faulted=True
            command(['patch','deployment/sglang-worker','--type=json','-p',json.dumps(patch)])
            released=True
            emit({'kind':'invalid_configuration_released','argument':BAD_ARG,'image_changed':False})
            deadline=time.monotonic()+120;drain=False;fired=[];crash=False
            while time.monotonic()<deadline:
                now=snapshot(old_url)
                old=now.get('old',{})
                if old.get('health')==503 and (old.get('running') or 0)>0: drain=True
                pods=read(['get','pods','-l','app=sglang-worker','-o','json'])['items']
                for pod in pods:
                    if pod['metadata']['uid']==old_pod['metadata']['uid']: continue
                    for status in pod.get('status',{}).get('containerStatuses',[]):
                        current=status.get('state',{});previous=status.get('lastState',{})
                        crash|=current.get('waiting',{}).get('reason')=='CrashLoopBackOff' or current.get('terminated',{}).get('exitCode',0)!=0 or previous.get('terminated',{}).get('exitCode',0)!=0
                fired=notification(now,seq,'firing')
                event={'kind':'maintenance','old_health':old.get('health'),'old_running':old.get('running'),
                       'gateway_status':now['gateway_status'],'healthy_workers':len(now['healthy_urls']),
                       'rule_state':now['rule_state'],'drain_observed':drain,'invalid_start_observed':crash,
                       'firing_received':bool(fired)}
                signature=json.dumps(event,sort_keys=True)
                if signature!=last: emit(event);last=signature
                if request.done.is_set() and drain and crash and fired and now['gateway_status']==503:
                    break
                time.sleep(0.5)
            else: raise TimeoutError('Drain/failure/firing notification not all observed in120s')
            assert request.result and request.result['ok'], 'Admitted request did not finish normally'
            emit({'kind':'admitted_request_completed',**request.result})
            emit({'kind':'firing_notification','events':fired})
            status,_=public_call(key,{'input_ids':[1000]*64,'stream':False,'sampling_params':{'max_new_tokens':1,'temperature':0}})
            emit({'kind':'planned_outage_request','status':status});assert status==503
        except BaseException as error:
            failure=error;emit({'kind':'experiment_failed','error':type(error).__name__})
        finally:
            try:
                if request and not request.done.is_set(): request.close()
                if faulted:
                    live=read(['get','deployment','sglang-worker','-o','json'])
                    if live['spec']['template']!=template:
                        assert live['spec']['template']['metadata'].get('annotations',{}).get(OWNER)==token, 'Rollback ownership changed; manual inspection required'
                        released=True
                        command(['rollout','undo','deployment/sglang-worker','--to-revision='+revision])
                        emit({'kind':'rollback_requested','original_revision':revision})
                    command(['rollout','status','deployment/sglang-worker','--timeout=1200s'],timeout=1220)
                    live=read(['get','deployment','sglang-worker','-o','json']);assert live['spec']['template']==template
                    emit({'kind':'rollback_template_restored','new_revision':live['metadata']['annotations'].get('deployment.kubernetes.io/revision')})
                def healthy_again():
                    value=snapshot();current=ready_pods()
                    if len(current)==1 and value['gateway_status']==200 and value['healthy_urls']==['http://'+current[0]['status']['podIP']+':30000']:
                        value['recovered_pod']={'name':current[0]['metadata']['name'],'uid':current[0]['metadata']['uid']}
                        return value
                restored=wait(healthy_again,90,'Gateway did not recover with the restored worker',emit)
                if released: assert restored['recovered_pod']['uid']!=old_pod['metadata']['uid'], 'Expected replacement Pod after rollback'
                recovered=True
                emit({'kind':'worker_available','pod':restored['recovered_pod']})
                if released:
                    def resolved():
                        value=snapshot();events=notification(value,seq,'resolved')
                        if value['rule_state']=='inactive' and events: return events
                    events=wait(resolved,90,'Resolved notification not received',emit)
                    emit({'kind':'resolved_notification','events':events})
                    status,body=public_call(key,{'input_ids':[1000]*64,'stream':False,'sampling_params':{'max_new_tokens':16,'ignore_eos':True,'temperature':0}})
                    assert status==200 and body['meta_info']['completion_tokens']==16
                    emit({'kind':'recovered_public_inference','status':status,'tokens':16})
            except BaseException as error:
                if failure is None: failure=error
                emit({'kind':'recovery_check_failed','error':type(error).__name__,'recovery':str(checkpoint)})
            finally:
                if paused and recovered:
                    try:
                        live_scaler=read(['get','scaledobject','sglang-worker-load','-o','json'])
                        live_annotations=live_scaler['metadata'].get('annotations',{})
                        if PAUSE in live_annotations or OWNER in live_annotations:
                            assert live_annotations.get(OWNER)==token, 'Pause ownership changed; manual inspection required'
                            command(['annotate','scaledobject/sglang-worker-load',PAUSE+'-',OWNER+'-'])
                        def resumed():
                            obj=read(['get','scaledobject','sglang-worker-load','-o','json']);c=conditions(obj)
                            return c.get('Paused')=='False' and c.get('Ready')=='True' and c.get('Fallback')=='False'
                        wait(resumed,90,'KEDA did not resume cleanly',emit)
                        emit({'kind':'autoscaling_restored'})
                    except BaseException as error:
                        if failure is None: failure=error
                        emit({'kind':'resume_failed','error':type(error).__name__,'recovery':str(checkpoint)})
                elif paused:
                    emit({'kind':'manual_recovery_required','reason':'Worker recovery not confirmed; KEDA remains paused','recovery':str(checkpoint)})
        if failure is not None:
            emit({'kind':'FAIL','error':type(failure).__name__,'recovery':str(checkpoint),'evidence':str(evidence)})
            raise SystemExit(1)
        emit({'kind':'PASS','inflight_drain':True,'invalid_configuration_detected':True,'private_firing_and_resolved_delivered':True,
              'rollback_restored_template':True,'external_inference_recovered':True,'autoscaling_restored':True,
              'scope':'single-replica intentional config failure with planned outage; not image upgrade, HA or hard-crash recovery','evidence':str(evidence)})


if __name__=='__main__': run_main(main)
