"""Offline regression tests for the clean-install-only data-disk setup."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / 'programas-callas-os/instalador/callas-storage-setup.py'
spec = importlib.util.spec_from_file_location('callas_storage_setup', HELPER)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
UUID = 'e1335b6b-460c-4ceb-a387-1ebaca3ff164'
ROOT = 'UUID=aaaa-bbbb / ext4 defaults 0 1\n'
EXT4 = f'UUID={UUID}\t/mnt/callas-{UUID}\text4\tnosuid,nodev,nofail,x-systemd.device-timeout=10s\t0\t0\n'
OTHER = 'UUID=AF48-98B3 /mnt/callas-af48-98b3 ntfs3 nosuid,nodev,nofail 0 0\n'
MARKED = ROOT + setup.MARKER + '\n' + EXT4 + OTHER


class PrepareMountTests(unittest.TestCase):
    def test_only_callas_ext4_is_made_fsck_enabled(self):
        result = setup.prepare_fstab(MARKED)
        self.assertTrue(result.startswith(ROOT))
        self.assertIn('x-systemd.before=local-fs.target', result)
        self.assertIn('ntfs3', result)
        self.assertEqual(result.count('x-systemd.before=local-fs.target'), 2)
        self.assertIn('errors=remount-ro\t0\t2\n', result)
        self.assertEqual(setup.candidates(result), [(f'/mnt/callas-{UUID}', UUID)])

    def test_idempotent_and_unrelated_rows_preserved(self):
        updated = setup.prepare_fstab(MARKED)
        self.assertEqual(updated, setup.prepare_fstab(updated))
        self.assertEqual(setup.prepare_fstab(ROOT + EXT4), ROOT + EXT4)
        self.assertIn('x-systemd.before=local-fs.target',
                      setup.prepare_fstab(ROOT + setup.MARKER + '\n' + OTHER))

    def test_malicious_and_system_paths_do_not_change(self):
        for source in ('UUID=bad space', 'UUID=invalid!!', 'LABEL=Games'):
            for target in ('/', '/home', '/mnt/callas-wrong', '/run/media/user/Games'):
                entry = f'{source} {target} ext4 nosuid,nodev,nofail 0 0\n'
                config = ROOT + setup.MARKER + '\n' + entry
                with self.subTest(source=source, target=target):
                    self.assertEqual(setup.prepare_fstab(config), config)

    def test_only_top_level_owner_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / 'games').mkdir()
            owner = SimpleNamespace(pw_uid=1000, pw_gid=1000)
            with (patch.object(Path, 'is_mount', return_value=True),
                  patch.object(Path, 'is_symlink', return_value=False),
                  patch.object(setup.os, 'chown') as chown,
                  patch.object(Path, 'stat') as metadata):
                metadata.return_value = SimpleNamespace(st_uid=0)
                setup.prepare_access(str(target), owner)
                chown.assert_called_once_with(target, 1000, 1000)

    def test_os_roots_and_other_owners_are_never_taken(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / 'etc').mkdir()
            owner = SimpleNamespace(pw_uid=1000, pw_gid=1000)
            with patch.object(Path, 'is_mount', return_value=True), patch.object(Path, 'is_symlink', return_value=False), patch.object(setup.os, 'chown') as chown:
                setup.prepare_access(str(target), owner)
                chown.assert_not_called()
                (target / 'etc').rmdir()
                with patch.object(Path, 'stat', return_value=SimpleNamespace(st_uid=1234)):
                    setup.prepare_access(str(target), owner)
                    chown.assert_not_called()

    def test_installer_downloads_verified_helper_before_wiping_disk(self):
        code = (REPO_ROOT / 'instalar-arch.sh').read_text()
        self.assertLess(code.index('CALLAS_STORAGE_STAGE'), code.index('wipefs -af "$DISCO"'))
        self.assertIn('install -m 0755 "$CALLAS_SECURITY_TMP/callas-automount.py"', code)
        self.assertIn('"$libexec/callas-storage-setup" "$usuario"', code)
        self.assertIn("digest != matches[0]['sha']", code)


if __name__ == '__main__':
    unittest.main()
