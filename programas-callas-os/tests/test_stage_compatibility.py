"""Run the actual shell bootstrap with an older installed launcher's file list."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];UP=ROOT/'atualizador'
spec=importlib.util.spec_from_file_location('stagingcompat',UP/'callas-release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class StageCompatibilityTests(unittest.TestCase):
    def test_complete_checks_every_current_file_and_rejects_insecure_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ['update-assets.json',*(Path(p).name for p in release.FILES)]:
                p=root/name;p.write_text('fixture');p.chmod(0o600)
            self.assertTrue(release.stage_complete(root,os.getuid()))
            helper=root/'callas-game-logs.py';helper.unlink()
            self.assertFalse(release.stage_complete(root,os.getuid()))
            helper.symlink_to(root/'VERSION')
            with self.assertRaisesRegex(ValueError,'simbólico'):release.stage_complete(root,os.getuid())
            helper.unlink();helper.write_text('fixture');helper.chmod(0o666)
            with self.assertRaisesRegex(ValueError,'inseguro'):release.stage_complete(root,os.getuid())
            helper.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'inseguro'):release.stage_complete(root,os.getuid()+1)

    def run_legacy_bootstrap(self, future=False, unsafe=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';stage=root/'stage';source.mkdir();stage.mkdir()
            counter=root/'requests';ref='a'*40
            names=list(release.FILES)
            module=(UP/'callas-release.py').read_text()
            # Fixture files are owned by the test runner, not by production root.
            module=module.replace('def stage_complete(destination, expected_owner=0):',f'def stage_complete(destination, expected_owner={os.getuid()}):')
            if future:
                names.append('programas-callas-os/atualizador/future-helper.py')
                module+='\nFILES += ("programas-callas-os/atualizador/future-helper.py",)\n'
            module+='''
# Fixture-only immutable network transport; real verification and staging run.
def request(url):
    from pathlib import Path
    with Path(COUNTER).open('a') as stream:stream.write(url+'\\n')
    if '/git/trees/' in url:return Path(TREE).read_bytes()
    return (Path(SOURCE)/url.rsplit('/',1)[-1]).read_bytes()
'''.replace('COUNTER',repr(str(counter))).replace('TREE',repr(str(root/'tree.json'))).replace('SOURCE',repr(str(source)))
            bodies={name:(module.encode() if name.endswith('/callas-release.py') else b'# fixture\n') for name in names}
            tree={'tree':[]}
            for name,body in bodies.items():
                target=source/Path(name).name;target.write_bytes(body)
                tree['tree'].append({'path':name,'type':'blob','mode':'100644','sha':hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()})
                if not name.endswith(('/callas-game-logs.py','/future-helper.py')):
                    dest=stage/Path(name).name;dest.write_bytes(body);dest.chmod(0o600)
            (root/'tree.json').write_text(json.dumps(tree))
            (stage/'update-assets.json').write_text('{}');(stage/'update-assets.json').chmod(0o600)
            if unsafe:(stage/'callas-game-logs.py').symlink_to(stage/'VERSION')
            updater=(UP/'callas-config-update.sh').read_text()
            block=updater[updater.index('if python - "$CALLAS_RELEASE_DIR" <<\'CHECK_STAGE\''):updater.index('\nexec 8>/run/put-update.lock')]
            code='set -Eeuo pipefail\nerro(){ echo "$*" >&2; exit 2; }\n'+block
            env=dict(os.environ,CALLAS_RELEASE_DIR=str(stage),CALLAS_RELEASE_REF=ref)
            result=subprocess.run(['bash','-c',code],env=env,capture_output=True,text=True)
            if unsafe:
                self.assertNotEqual(result.returncode,0)
                self.assertIn('insegura',result.stderr)
                self.assertFalse(counter.exists())
                self.assertTrue((stage/'callas-game-logs.py').is_symlink())
                return
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue((stage/'callas-game-logs.py').is_file())
            if future:self.assertTrue((stage/'future-helper.py').is_file())
            self.assertTrue(counter.exists())
            before=counter.read_bytes()
            self.assertTrue(all('/'+ref in line for line in before.decode().splitlines()))
            result=subprocess.run(['bash','-c',code],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(counter.read_bytes(),before,'complete stage downloaded again')

    def test_old_launcher_missing_game_helper_expands_once(self):self.run_legacy_bootstrap()
    def test_future_helpers_do_not_require_another_shell_allowlist(self):self.run_legacy_bootstrap(future=True)
    def test_unsafe_stage_fails_before_any_download(self):self.run_legacy_bootstrap(unsafe=True)

if __name__=='__main__':unittest.main()
