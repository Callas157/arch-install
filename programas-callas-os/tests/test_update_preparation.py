"""Offline preparation: concurrent transport, progress and fail-closed validation."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preparation', ROOT/'atualizador/callas-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class PreparationTests(unittest.TestCase):
    def test_installation_can_prepare_silently_without_disabling_blob_verification(self):
        name='programas-callas-os/a.py'
        body=b'# verified fixture\n'
        sha=hashlib.sha1(b'blob 19\0'+body).hexdigest()
        tree={'tree':[{'path':name,'type':'blob','mode':'100644','sha':sha}]}
        for corrupt in (False,True):
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory() as temp:
                output=io.StringIO()
                def request(url):
                    if '/git/trees/' in url:return json.dumps(tree).encode()
                    return b'# tampered\n' if corrupt else body
                with patch.object(release,'FILES',(name,)),patch.object(release,'request',request),redirect_stdout(output):
                    if corrupt:
                        with self.assertRaisesRegex(ValueError,'blob'):
                            release.stage_files(temp,'a'*40,progress=False)
                        self.assertFalse((Path(temp)/'a.py').exists())
                    else:
                        release.stage_files(temp,'a'*40,progress=False)
                        self.assertEqual((Path(temp)/'a.py').read_bytes(),body)
                self.assertEqual(output.getvalue(),'')

    def test_downloads_overlap_and_report_progress_before_waiting(self):
        names = ('programas-callas-os/a.py', 'programas-callas-os/b.py')
        barrier = threading.Barrier(2)
        output = io.StringIO()
        body = b'# verified fixture\n'
        sha = hashlib.sha1(b'blob 19\0' + body).hexdigest()
        tree = {'tree': [{'path': name, 'type': 'blob', 'mode': '100644', 'sha': sha} for name in names]}
        def request(url):
            if '/git/trees/' in url:
                self.assertTrue(output.getvalue(), 'preparation must respond before the network')
                return json.dumps(tree).encode()
            barrier.wait(timeout=2)
            return body
        with tempfile.TemporaryDirectory() as temp, patch.object(release, 'FILES', names), patch.object(release, 'request', request), redirect_stdout(output):
            release.stage_files(temp, 'a'*40)
            self.assertEqual((Path(temp)/'a.py').read_bytes(), body)
            self.assertEqual((Path(temp)/'b.py').read_bytes(), body)
            self.assertIn('2/2', output.getvalue())

    def test_invalid_download_never_reaches_migration(self):
        name = 'programas-callas-os/a.py'
        tree = {'tree': [{'path': name, 'type': 'blob', 'mode': '100644', 'sha': 'b'*40}]}
        def request(url):
            return json.dumps(tree).encode() if '/git/trees/' in url else b'print("tampered")\n'
        with tempfile.TemporaryDirectory() as temp, patch.object(release, 'FILES', (name,)), patch.object(release, 'request', request), patch.object(release.subprocess, 'run') as execute:
            with self.assertRaisesRegex(ValueError, 'blob'):
                release.stage_files(temp, 'a'*40)
            self.assertFalse((Path(temp)/'a.py').exists())
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
