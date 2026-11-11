"""Offline project-version and folder migration tests, without system changes."""
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / 'programas-callas-os/atualizador'

def load(name):
    spec = importlib.util.spec_from_file_location(name, UPDATER / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

version = load('callas-version'); storage = load('callas-storage'); logs = load('callas-logs')
REF = 'a' * 40

class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.file = self.base / 'VERSION'; self.file.write_text('3.2.0\n')
        self.state = patch.object(version, 'STATE', self.base / 'etc/release.json'); self.state.start()
    def tearDown(self): self.state.stop(); self.temp.cleanup()
    def test_pending_and_failed_updates_do_not_claim_new_version(self):
        version.transition('--begin', self.file, REF)
        self.assertEqual(version.label(), 'Callas OS (Arch Linux)')
        version.transition('--fail', self.file, REF)
        self.assertIsNone(version.read_state()['version'])
        self.assertEqual(version.read_state()['status'], 'incomplete')
    def test_complete_then_failed_upgrade_keeps_last_completed_version(self):
        version.transition('--begin', self.file, REF); version.transition('--complete', self.file, REF)
        self.assertEqual(version.label(), 'Callas OS v3.2.0 (Arch Linux)')
        self.file.write_text('3.3.0\n'); version.transition('--begin', self.file, REF)
        version.transition('--fail', self.file, REF)
        self.assertEqual(version.read_state()['version'], '3.2.0')
        self.assertIn('destino: v3.3.0', version.context())
    def test_legacy_boot_is_marked_without_claiming_full_release(self):
        version.transition('--begin', self.file, REF); version.transition('--blocked', self.file, REF)
        self.assertIsNone(version.read_state()['version'])
        self.assertEqual(version.read_state()['status'], 'incompatible-boot')
    def test_wrong_transaction_cannot_complete(self):
        version.transition('--begin', self.file, REF)
        with self.assertRaises(ValueError): version.transition('--complete', self.file, 'b' * 40)
        self.assertIsNone(version.read_state()['version'])
    def test_invalid_version_cannot_write_state(self):
        self.file.write_text('3.2.0; touch /tmp/unsafe')
        with self.assertRaises(ValueError): version.transition('--begin', self.file, REF)
        self.assertFalse(version.STATE.exists())
    def test_state_is_publicly_readable_and_atomically_replaced(self):
        version.transition('--begin', self.file, REF); version.transition('--complete', self.file, REF)
        self.assertEqual(version.STATE.stat().st_mode & 0o777, 0o644)
        self.assertEqual(version.STATE.parent.stat().st_mode & 0o777, 0o755)
        self.assertEqual(list(version.STATE.parent.glob('.release-*')), [])
    def test_neko_preserves_style_and_other_rows_and_reads_version_dynamically(self):
        path = self.base / 'layout.jsonc'
        path.write_text('''{ // comment
          "logo":{"source":"https://example.org/art"},
          "modules":[{"type":"os","key":"  icon OS  ","keyColor":"magenta","format":"{pretty-name}"},
          {"type":"gpu","format":"{name}"},],}''')
        version.configure_neko(path); first = path.read_text(); version.configure_neko(path)
        self.assertEqual(path.read_text(), first)
        layout = json.loads(first); row = layout['modules'][0]
        self.assertEqual(row['text'], version.COMMAND); self.assertEqual(row['keyColor'], 'magenta')
        self.assertEqual(row['key'], '  icon OS  '); self.assertNotIn('format', row)
        self.assertEqual(layout['modules'][1], {'type':'gpu', 'format':'{name}'})
        self.assertEqual(layout['logo']['source'], 'https://example.org/art')
        version.transition('--begin', self.file, REF); version.transition('--complete', self.file, REF)
        self.assertIn('v3.2.0', version.label()); self.assertEqual(path.read_text(), first)
    def test_missing_os_row_leaves_layout_unchanged(self):
        path = self.base / 'layout.jsonc'; path.write_text('{"modules":["cpu"]}')
        with self.assertRaises(ValueError): version.configure_neko(path)
        self.assertEqual(path.read_text(), '{"modules":["cpu"]}')
    def test_embedded_neko_matches_staged_helper(self):
        installer = (ROOT / 'instalar-arch.sh').read_text()
        body = installer.split("<<'CALLAS_NEKO'\n", 1)[1].split('\nCALLAS_NEKO\n', 1)[0]
        self.assertEqual(body + '\n', (UPDATER / 'callas-nekofetch.sh').read_text())
        self.assertRegex((UPDATER / 'VERSION').read_text().strip(), version.SEMVER)
    def test_metadata_stays_inside_programs_with_original_root_entrypoints(self):
        for name in ('VERSION', 'CHANGELOG.md', 'AGENTS.md'):
            self.assertFalse((ROOT / name).exists(), name)
        self.assertTrue((UPDATER / 'VERSION').is_file())
        self.assertTrue((UPDATER / 'CHANGELOG.md').is_file())
        self.assertTrue((ROOT / 'programas-callas-os/AGENTS.md').is_file())
        self.assertTrue((ROOT / 'callas-config-update.sh').is_file())
        self.assertTrue((ROOT / 'instalar-arch.sh').is_file())

class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.account = pwd.getpwuid(os.getuid())
        self.uid = patch.object(storage, 'ROOT_UID', os.getuid()); self.uid.start()
        self.policy = patch.object(storage, 'POLICY', self.base / 'policy'); self.policy.start()
    def tearDown(self): self.policy.stop(); self.uid.stop(); self.temp.cleanup()
    def open(self): return storage.Backups(self.account.pw_name, documents=self.base)
    def test_whole_previous_backup_pool_is_moved_with_private_archive(self):
        old = self.base / 'Callas OS Backup'; folder = old / 'Sistema'; folder.mkdir(parents=True)
        file = folder / '20261111-120000-000000000001.tar.gz'; file.write_bytes(b'private'); file.chmod(0o600)
        with self.open() as backups:
            self.assertEqual(backups.path, self.base / 'Callas OS/Callas OS Backups')
            self.assertEqual((backups.path / 'Sistema' / file.name).read_bytes(), b'private')
            self.assertEqual((backups.path / 'Sistema' / file.name).stat().st_mode & 0o777, 0o600)
        self.assertFalse(old.exists())
        with self.open() as backups: self.assertEqual(len(backups.entries()), 1)
    def test_simultaneous_pools_are_merged_without_overwriting_duplicates(self):
        with self.open() as backups:
            old = self.base / 'Callas OS Backup/Sistema'; old.mkdir(parents=True)
            name = '20261111-120000-000000000001.tar.gz'
            (old / name).write_bytes(b'old'); (backups.path / 'Sistema' / name).write_bytes(b'new')
            another = '20261111-120000-000000000002.tar.gz'; (old / another).write_bytes(b'move')
            backups.migrate_document_pools(); backups.migrate_document_pools()
            self.assertEqual((old / name).read_bytes(), b'old')
            self.assertEqual((backups.path / 'Sistema' / name).read_bytes(), b'new')
            self.assertEqual((backups.path / 'Sistema' / another).read_bytes(), b'move')
    def test_symlink_project_cannot_redirect_privileged_writes(self):
        outside = self.base / 'outside'; outside.mkdir()
        (self.base / 'Callas OS').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError): self.open()
        self.assertEqual(list(outside.iterdir()), [])
    def test_archive_contains_version_manifest(self):
        with self.open() as backups:
            name = backups.create('Sistema', [])
            with tarfile.open(backups.path / 'Sistema' / name) as archive:
                data = json.load(archive.extractfile('callas-release.json'))
                self.assertIn('version', data)
    def test_legacy_archive_does_not_claim_the_current_version(self):
        with self.open() as backups:
            name = backups.create('Sistema', [], legacy=True)
            with tarfile.open(backups.path / 'Sistema' / name) as archive:
                data = json.load(archive.extractfile('callas-release.json'))
                self.assertEqual(data, {'version': None, 'status': 'legacy-import'})
    def test_both_old_log_roots_move_under_one_project_without_loss(self):
        for folder in ('Callas OS Logs', 'Logs do Callas OS'):
            path = self.base / folder / 'AUR'; path.mkdir(parents=True); (path / 'old.log').write_text(folder)
        with patch.object(logs, 'documents', return_value=self.base), patch.object(logs.os, 'geteuid', return_value=1000):
            root = logs.prepare(); logs.prepare()
        self.assertEqual(root, self.base / 'Callas OS/Callas OS Logs')
        self.assertEqual({p.read_text() for p in root.rglob('old.log')}, {'Callas OS Logs', 'Logs do Callas OS'})
        self.assertFalse((self.base / 'Callas OS Logs').exists())
    def test_imported_diagnostic_never_receives_a_fabricated_version(self):
        with patch.object(logs, 'documents', return_value=self.base), patch.object(logs.os, 'geteuid', return_value=1000), patch.object(logs, 'identified', side_effect=AssertionError('must preserve imported bytes')):
            file = logs.write_log('AUR', b'old event', origin='old.log')
        self.assertEqual(file.read_bytes(), b'old event')

if __name__ == '__main__': unittest.main()
