import contextlib
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class ValidationScopeTests(unittest.TestCase):
    def run_fixture(self,public_invalid=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ['scripts','benchmarks','results/legacy','.private','.venv']:
                (root/name).mkdir(parents=True,exist_ok=True)
            shutil.copy(ROOT/'scripts/validate.py',root/'scripts/validate.py')
            (root/'scripts/smoke.py').write_text('pass\n')
            (root/'benchmarks/run.py').write_text('pass\n')
            (root/'results/legacy/manifest.json').write_text('{"files":[]}')
            (root/'.private/never-parse.json').write_text('private invalid fixture')
            (root/'.venv/never-parse.json').write_text('venv invalid fixture')
            if public_invalid:(root/'public-invalid.json').write_text('invalid public fixture')
            config={'services':{'sglang':{'image':'fixture@sha256:fixture','ports':[]}}}
            result=subprocess.CompletedProcess(['docker'],0,stdout=json.dumps(config),stderr='')
            with patch.object(subprocess,'run',return_value=result),contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(root/'scripts/validate.py'),run_name='__main__')

    def test_private_and_virtualenv_json_are_not_parsed(self):
        self.run_fixture()

    def test_public_invalid_json_still_fails(self):
        with self.assertRaises(json.JSONDecodeError):self.run_fixture(public_invalid=True)


if __name__=='__main__':unittest.main()
