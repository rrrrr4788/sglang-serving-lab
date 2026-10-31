"""Offline safety checks: no SSH, Kubernetes or installation is performed."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cloud', Path(__file__).resolve().parents[1] / 'scripts/cloud/cloud.py')
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class CloudSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name)
        self.config = self.private / 'cloud-kubeconfig'
        self.a = SimpleNamespace(host='new.example', user='ubuntu', key='/private/key', ssh_port=22, api_port=16443)
        self.raw = {'clusters': [{'name': 'default', 'cluster': {'server': 'https://127.0.0.1:6443', 'certificate-authority-data': 'CA'}}],
                    'users': [{'name': 'default', 'user': {'client-key-data': 'SECRET_FIXTURE'}}],
                    'contexts': [{'name': 'default', 'context': {'cluster': 'default', 'user': 'default'}}]}
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(cloud, 'PRIVATE', self.private))
        stack.enter_context(patch.object(cloud, 'KUBECONFIG', self.config))

    def connect_responses(self, uid):
        return [json.dumps(self.raw).encode(), b'expected-cluster', json.dumps({'metadata': {'uid': uid}}).encode()]

    def test_identity_mismatch_preserves_old_config(self):
        self.config.write_bytes(b'old-private-config')
        with patch.object(cloud, 'run', side_effect=self.connect_responses('wrong-cluster')):
            with self.assertRaisesRegex(RuntimeError, 'identity differs'):
                cloud.connect(self.a)
        self.assertEqual(self.config.read_bytes(), b'old-private-config')
        self.assertEqual(list(self.private.glob('.cloud-check-*')), [])

    def test_config_import_preserves_tls_and_backs_up_privately(self):
        self.config.write_bytes(b'old-private-config')
        output = io.StringIO()
        with patch.object(cloud, 'run', side_effect=self.connect_responses('expected-cluster')), contextlib.redirect_stdout(output):
            cloud.connect(self.a)
        cfg = json.loads(self.config.read_bytes())
        self.assertEqual(cfg['clusters'][0]['cluster'], {'server': 'https://127.0.0.1:16443', 'certificate-authority-data': 'CA'})
        self.assertEqual(cfg['current-context'], cloud.CONTEXT)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        backups = list(self.private.glob('cloud-kubeconfig.backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'old-private-config')
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertNotIn('SECRET_FIXTURE', output.getvalue())

    def test_occupied_port_never_reuses_existing_tunnel(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.a.api_port = listener.getsockname()[1]
            listener.listen()
            with patch.object(cloud.subprocess, 'Popen') as popen:
                with self.assertRaisesRegex(RuntimeError, 'occupied'):
                    with cloud.tunnel(self.a):
                        self.fail('Must reject an unknown listener')
                popen.assert_not_called()

    def test_tunnel_binds_loopback_and_cleans_up(self):
        with patch.object(cloud.socket, 'socket'), patch.object(cloud.socket, 'create_connection'), patch.object(cloud.subprocess, 'Popen') as popen:
            process = popen.return_value
            process.poll.return_value = None
            with cloud.tunnel(self.a):
                pass
            args = popen.call_args.args[0]
            self.assertEqual(args.count('ubuntu@new.example'), 1)
            self.assertIn('127.0.0.1:16443:127.0.0.1:6443', args)
            self.assertIn('StrictHostKeyChecking=yes', args)
            process.terminate.assert_called_once()

    def test_captured_command_failure_does_not_echo_private_output(self):
        result = subprocess.CompletedProcess(['kubectl'], 1, stdout=b'SECRET_FIXTURE', stderr=b'SECRET_FIXTURE')
        with patch.object(cloud.subprocess, 'run', return_value=result):
            with self.assertRaises(RuntimeError) as error:
                cloud.run(['kubectl'], capture=True)
        self.assertNotIn('SECRET_FIXTURE', str(error.exception))


class HostRegistrationTests(unittest.TestCase):
    def test_missing_node_is_waited_for_before_ready(self):
        # Replay initial NotFound at the actual host-script call site.
        source = (Path(__file__).resolve().parents[1] / 'scripts/cloud/bootstrap-host.sh').read_text()
        start = source.index('k=(k3s kubectl ')
        stop = source.index('"${k[@]}" get runtimeclass')
        stage = source[start:stop]
        fixture = ('set -euo pipefail\nregistered=0\nk3s() {\n'
                   '  case " $* " in\n'
                   '    *" --for=create "*) registered=1;;\n'
                   '    *" --for=condition=Ready "*)\n'
                   '      if [[ $registered == 0 ]]; then\n'
                   '        printf \'Error from server (NotFound): nodes "sglang-gpu-01" not found\\n\' >&2\n'
                   '        return 1\n'
                   '      fi\n'
                   '      printf \'node condition met\\n\';;\n'
                   '    *) return 2;;\n'
                   '  esac\n}\n')
        result = subprocess.run(['bash', '-c', fixture + stage], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('node condition met', result.stdout)


if __name__ == '__main__':
    unittest.main()
