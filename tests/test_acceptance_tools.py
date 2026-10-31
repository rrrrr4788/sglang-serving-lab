import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/acceptance'))
import common

spec=importlib.util.spec_from_file_location('prepare_https',ROOT/'scripts/cloud/prepare_https.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


class AcceptanceToolsTests(unittest.TestCase):
    def test_sse_framing_done_and_truncation(self):
        frames=[b': heartbeat\n',b'data: {"n":1}\r\n',b'\r\n',b'data: [DONE]\n',b'\n']
        self.assertEqual(list(common.sse_events(frames)),[{'n':1},None])
        with self.assertRaises(RuntimeError): list(common.sse_events([b'data: {}\n']))
        with self.assertRaises(RuntimeError): list(common.sse_events([b'data: {"error":"fixture"}\n',b'\n']))

    def test_origin_rejects_credential_forwarding_targets(self):
        for url in ['http://example.com','https://u:p@example.com','https://example.com/path','https://example.com?token=fixture','https://example.com:8443']:
            with self.subTest(url=url),self.assertRaises(ValueError): common.https_origin(url)
        self.assertEqual(common.https_origin('https://example.com/'),'https://example.com')
        self.assertIsNone(common.NoRedirect().redirect_request(None,None,302,'',{},'https://other.invalid'))

    def test_wrong_cluster_fails_before_dns_and_evidence(self):
        parser=argparse.ArgumentParser();common.add_target_arguments(parser,public=True)
        a=parser.parse_args(['--host','192.0.2.10','--base-url','https://example.invalid'])
        result=SimpleNamespace(returncode=0,stdout=json.dumps({'status':{'addresses':[{'address':'192.0.2.11'}]}}))
        with patch.object(common.subprocess,'run',return_value=result),patch.object(common.socket,'getaddrinfo') as dns:
            with self.assertRaises(RuntimeError): common.configure_target(a,public=True)
            dns.assert_not_called()

    def test_dns_target_and_explicit_context(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            parser=argparse.ArgumentParser();common.add_target_arguments(parser,public=True)
            a=parser.parse_args(['--host','192.0.2.10','--base-url','https://example.invalid','--context','fixture-context','--evidence-dir',str(root/'.private/evidence')])
            calls=[]
            def run(cmd,**kwargs):
                calls.append(cmd)
                value={'status':{'addresses':[{'address':'192.0.2.10'}]}} if 'node' in cmd else {'metadata':{'uid':'fixture-cluster'}}
                return SimpleNamespace(returncode=0,stdout=json.dumps(value))
            with patch.object(common,'ROOT',root),patch.object(common.subprocess,'run',side_effect=run),patch.object(common.socket,'getaddrinfo',return_value=[(None,None,None,None,('192.0.2.11',443))]):
                with self.assertRaises(RuntimeError): common.configure_target(a,public=True)
                self.assertFalse(a.evidence_dir.exists())
            with patch.object(common,'ROOT',root),patch.object(common.subprocess,'run',side_effect=run),patch.object(common.socket,'getaddrinfo',return_value=[(None,None,None,None,('192.0.2.10',443))]),contextlib.redirect_stdout(io.StringIO()):
                target=common.configure_target(a,public=True)
            self.assertEqual(target.base_url,'https://example.invalid')
            self.assertTrue(target.evidence.is_dir())
            for cmd in calls:
                self.assertEqual(cmd[cmd.index('--context')+1],'fixture-context')
                self.assertIn('--kubeconfig',cmd)

    def test_private_key_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'fixture.key';p.write_text('a'*64);p.chmod(0o644)
            with self.assertRaises(ValueError): common.private_key(p)
            p.chmod(0o600);self.assertEqual(common.private_key(p),'a'*64)

    def test_https_render_is_local_private_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'deploy/k3s').mkdir(parents=True)
            shutil.copy(ROOT/'deploy/k3s/inference-ingress.yaml',root/'deploy/k3s/inference-ingress.yaml')
            output=root/'.private/rendered'
            with patch.object(prepare,'ROOT',root):
                paths=prepare.render('192.0.2.10','sglang-192-0-2-10.sslip.io',output,'fixture@example.invalid')
                original=[p.read_bytes() for p in paths]
                self.assertTrue(all(p.stat().st_mode & 0o077==0 for p in paths))
                with self.assertRaises(FileExistsError): prepare.render('192.0.2.11','other.example.invalid',output,'other@example.invalid')
                self.assertEqual([p.read_bytes() for p in paths],original)
                with self.assertRaises(ValueError): prepare.render('192.0.2.10','example.invalid',root/'public','fixture@example.invalid')

    def test_fresh_copy_help_and_no_side_effect_gates(self):
        # Public files only; no .private, current kubeconfig, key or cluster is available.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            shutil.copytree(ROOT/'scripts',root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            for name in ['ready','https','stream_cancel','operations','autoscaling']:
                script=root/'scripts/acceptance'/(name+'.py')
                p=subprocess.run([sys.executable,str(script),'--help'],capture_output=True,text=True,timeout=5)
                self.assertEqual(p.returncode,0,p.stderr)
                args=['--host','192.0.2.10']
                if name in ['https','stream_cancel','operations']:args+=['--base-url','https://example.invalid']
                p=subprocess.run([sys.executable,str(script),*args],capture_output=True,text=True,timeout=5)
                self.assertEqual(p.returncode,2,p.stderr)
            self.assertFalse((root/'.private').exists())


if __name__=='__main__': unittest.main()
