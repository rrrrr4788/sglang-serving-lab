import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/cloud'))
launch = importlib.import_module('launch')


class CloudLaunchTests(unittest.TestCase):
    def test_concurrent_launch_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'host.lock'
            with launch.deployment_lock(path):
                with self.assertRaises(RuntimeError):
                    with launch.deployment_lock(path):
                        self.fail('Concurrent launch must not enter')
            with launch.deployment_lock(path):
                pass

    def test_plan_is_public_only_and_side_effect_free(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            shutil.copytree(ROOT/'scripts',root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            p=subprocess.run([sys.executable,str(root/'scripts/cloud/launch.py'),'--host','192.0.2.10','--plan'],
                             capture_output=True,text=True,timeout=5)
            self.assertEqual(p.returncode,0,p.stderr)
            data=json.loads(p.stdout)
            self.assertEqual(data['stages'],launch.STAGES)
            self.assertEqual(data['hostname'],'sglang-192-0-2-10.sslip.io')
            self.assertFalse(data['automatic_teardown'])
            self.assertFalse((root/'.private').exists())

    def test_checkpoint_failure_retry_and_input_pins(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'new/state.json'
            cp=launch.Checkpoint(path,{'host':'192.0.2.10'},'source-a',False)
            def fail():raise RuntimeError('fixture')
            with self.assertRaises(RuntimeError):cp.stage('apps',fail)
            self.assertEqual(cp.data['done'],[])
            again=launch.Checkpoint(path,{'host':'192.0.2.10'},'source-a',True)
            self.assertEqual(again.data['owner'],cp.data['owner'])
            again.stage('apps',lambda:None)
            again.stage('apps',lambda:self.fail('Accepted stage must not reapply'))
            self.assertEqual(again.data['done'],['apps'])
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            for identity,source,resume in [({'host':'192.0.2.11'},'source-a',True),
                                           ({'host':'192.0.2.10'},'source-b',True),
                                           ({'host':'192.0.2.10'},'source-a',False)]:
                with self.assertRaises(RuntimeError):launch.Checkpoint(path,identity,source,resume)

    def test_unowned_local_directory_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';other=path.parent/'foreign';other.write_text('keep')
            with self.assertRaises(RuntimeError):launch.Checkpoint(path,{},'fixture',False)
            self.assertEqual(other.read_text(),'keep')

    def test_reused_ip_rejects_before_host_or_apps(self):
        cp=SimpleNamespace(data={'cluster_uid':'old-cluster','done':['host']})
        a=SimpleNamespace(host='192.0.2.10',user='ubuntu',key='fixture',ssh_port=22)
        with patch.object(launch.cloud,'run',return_value=b'different-cluster'),patch.object(launch.cloud,'host') as host:
            with self.assertRaises(RuntimeError):launch.pipeline(a,cp,Path('/unused'))
            host.assert_not_called()

    def test_namespace_owner_and_uid_guards(self):
        cp=SimpleNamespace(data={'owner':'ours','namespace_uid':'original-ns'},save=lambda:None)
        for owner,uid in [('foreign','original-ns'),('ours','replacement-ns')]:
            raw=json.dumps({'metadata':{'uid':uid,'annotations':{launch.OWNER:owner}}}).encode()
            with patch.object(launch.cloud,'run',return_value=raw) as run:
                with self.assertRaises(RuntimeError):launch.claim_namespace(cp)
                self.assertEqual(run.call_count,1)

    def test_bad_cache_and_download_are_not_installed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cached';path.write_bytes(b'corrupted')
            with patch.object(launch.urllib.request,'urlopen') as request:
                with self.assertRaises(RuntimeError):launch.fetch_verified(path,'https://example.invalid','a'*64)
                request.assert_not_called()
            self.assertEqual(path.read_bytes(),b'corrupted')
            path.unlink()
            response=SimpleNamespace(geturl=lambda:'https://example.invalid',read=lambda n:b'wrong-download')
            with patch.object(launch.urllib.request,'urlopen',return_value=contextlib.nullcontext(response)):
                with self.assertRaises(RuntimeError):launch.fetch_verified(path,'https://example.invalid','a'*64)
            self.assertFalse(path.exists())

    def test_tools_are_verified_again_before_use(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            buffer=io.BytesIO()
            with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
                data=b'fixture-helm-not-executed';entry=tarfile.TarInfo('linux-amd64/helm');entry.size=len(data)
                tar.addfile(entry,io.BytesIO(data))
            blobs={'helm-v3.22.1-linux-amd64.tar.gz':buffer.getvalue(),'keda-2.21.0.tgz':b'keda-fixture','traefik-42.1.3.tgz':b'edge-fixture'}
            artifacts={name:('https://example.invalid/'+name,hashlib.sha256(blob).hexdigest()) for name,blob in blobs.items()}
            def fetch(path,url,digest):launch.atomic(path,blobs[path.name])
            with patch.object(launch,'ROOT',root),patch.object(launch,'ARTIFACTS',artifacts),patch.object(launch,'fetch_verified',side_effect=fetch):
                launch.prepare_tools();launch.verify_tools()
                (root/'.private/bin/helm').write_bytes(b'changed')
                with self.assertRaises(RuntimeError):launch.verify_tools()

    def test_render_publish_lost_ack_is_resumable(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'deploy/k3s').mkdir(parents=True)
            shutil.copy(ROOT/'deploy/k3s/inference-ingress.yaml',root/'deploy/k3s/inference-ingress.yaml')
            contact=root/'contact.json';contact.write_text(json.dumps({'certificatesResolvers':{'le':{'acme':{'email':'fixture@example.invalid'}}}}))
            cp=launch.Checkpoint(root/'.private/deployments/fixture/state.json',{},'source',False)
            directory=cp.path.parent/'https'
            a=SimpleNamespace(host='192.0.2.10',hostname='example.invalid',contact_file=contact)
            rename=launch.os.rename
            def lost(src,dst):rename(src,dst);raise OSError('lost after publishing')
            with patch.object(launch.prepare_https,'ROOT',root),patch.object(launch.os,'rename',side_effect=lost):
                with self.assertRaises(OSError):launch.render_inputs(a,cp,directory)
            with patch.object(launch.getpass,'getpass') as prompt:
                launch.render_inputs(a,cp,directory)
                prompt.assert_not_called()
            launch.verify_inputs(cp,directory)
            (directory/'inference-ingress.yaml').write_text('changed')
            with self.assertRaises(RuntimeError):launch.verify_inputs(cp,directory)

    def test_pipeline_replays_failed_app_stage_without_repeating_host(self):
        with tempfile.TemporaryDirectory() as folder:
            cp=launch.Checkpoint(Path(folder)/'record/state.json',{},'source',False)
            a=SimpleNamespace(host='192.0.2.10',hostname='example.invalid',user='ubuntu',key='fixture',ssh_port=22)
            def read(args):
                if args[1]=='namespace':return {'metadata':{'uid':'cluster'}}
                if args[1]=='node':return {'status':{'addresses':[{'address':a.host}]}}
                return {'status':{'conditions':[{'type':'Ready','status':'True'},{'type':'Fallback','status':'False'}]}}
            def render(*args):
                cp.data['input_hashes']={'fixture':'fixture'};cp.save()
            responses=[RuntimeError('interrupted application'),None]
            snapshot={'gateway_status':200,'healthy_urls':['http://fixture:30000'],'rule_state':'inactive','rule_health':'ok','alertmanager_status':200}
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(launch,'render_inputs',side_effect=render))
                for name in ['verify_inputs','verify_tools','dns_matches','claim_namespace','install_edge','wait_tls']:
                    stack.enter_context(patch.object(launch,name))
                tools=stack.enter_context(patch.object(launch,'prepare_tools'))
                host=stack.enter_context(patch.object(launch.cloud,'host'))
                stack.enter_context(patch.object(launch.cloud,'tunnel',side_effect=lambda _:contextlib.nullcontext()))
                stack.enter_context(patch.object(launch.cloud,'connect'))
                stack.enter_context(patch.object(launch.cloud,'run',return_value=b'cluster'))
                deploy=stack.enter_context(patch.object(launch.cloud,'deploy',side_effect=responses))
                stack.enter_context(patch.object(launch,'read',side_effect=read))
                stack.enter_context(patch.object(launch,'enable_scaling'))
                calls=stack.enter_context(patch.object(launch,'acceptance',return_value=json.dumps(snapshot).encode()))
                with self.assertRaises(RuntimeError):launch.pipeline(a,cp,Path(folder)/'https')
                self.assertEqual(cp.data['in_progress'],'apps')
                again=launch.Checkpoint(cp.path,{},'source',True)
                launch.pipeline(a,again,Path(folder)/'https')
                self.assertEqual(again.data['done'],launch.STAGES)
                host.assert_called_once();tools.assert_called_once()
                self.assertEqual(deploy.call_count,2)
                self.assertTrue(any(call.args[1]=='https.py' for call in calls.call_args_list))

    def test_final_snapshot_cannot_turn_an_outage_into_ready(self):
        value={'gateway_status':503,'healthy_urls':[],'rule_state':'firing','rule_health':'ok','alertmanager_status':200}
        a=SimpleNamespace()
        with patch.object(launch,'acceptance',return_value=json.dumps(value).encode()),patch.object(launch,'read',return_value={}),patch.object(launch.time,'monotonic',side_effect=[0,100]):
            with self.assertRaises(RuntimeError):launch.final_checks(a,seconds=1)

    def test_existing_foreign_keda_namespace_is_not_upgraded(self):
        cloud=launch.cloud
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.private/bin').mkdir(parents=True);(root/'.private/vendor').mkdir()
            (root/'.private/bin/helm').write_bytes(b'fixture')
            chart=root/'.private/vendor/keda-2.21.0.tgz';chart.write_bytes(b'fixture-chart')
            responses=[json.dumps({'items':[]}).encode(),
                       json.dumps({'metadata':{'annotations':{launch.OWNER:'ours'}}}).encode(),
                       json.dumps({'metadata':{'annotations':{launch.OWNER:'someone-else'}}}).encode()]
            with patch.object(cloud,'ROOT',root),patch.object(cloud,'CHART_SHA',hashlib.sha256(chart.read_bytes()).hexdigest()),patch.object(cloud,'run',side_effect=responses) as run:
                with self.assertRaises(RuntimeError):cloud.deploy(SimpleNamespace(),owner='ours')
                self.assertEqual(run.call_count,3)
                self.assertTrue(all('apply' not in call.args[0] for call in run.call_args_list))

    def test_owned_resume_guard_runs_before_secret_or_apply(self):
        cloud=launch.cloud
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.private/bin').mkdir(parents=True);(root/'.private/vendor').mkdir()
            (root/'.private/bin/helm').write_bytes(b'fixture')
            chart=root/'.private/vendor/keda-2.21.0.tgz';chart.write_bytes(b'fixture-chart')
            responses=[json.dumps({'items':[{'metadata':{'namespace':cloud.NS,'name':'sglang-worker'}}]}).encode(),
                       json.dumps({'metadata':{'annotations':{launch.OWNER:'foreign'}}}).encode()]
            with patch.object(cloud,'ROOT',root),patch.object(cloud,'CHART_SHA',hashlib.sha256(chart.read_bytes()).hexdigest()),patch.object(cloud,'run',side_effect=responses) as run:
                with self.assertRaises(RuntimeError):cloud.deploy(SimpleNamespace(),owner='ours')
                self.assertEqual(run.call_count,2)
                self.assertTrue(all('apply' not in call.args[0] for call in run.call_args_list))


if __name__=='__main__':unittest.main()
