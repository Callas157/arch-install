import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import stat
import sys
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'atualizador/callas-steam-libraries.py'
spec = importlib.util.spec_from_file_location('steam_storage', SOURCE)
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.base = Path(self.temp)
        self.home = self.base / 'home'
        self.steam = self.home / '.local/share/Steam'
        self.catalogs = [self.steam / part / 'libraryfolders.vdf'
                         for part in ('steamapps', 'config')]
        self.mount = self.base / 'Jogos NVMe'
        self.mount.mkdir()
        self.initial = self.profile()
        self.running = self.enterContext(patch.object(helper, 'steam_running', return_value=False))
        self.mounts = self.enterContext(patch.object(helper, 'find_mounts', return_value={self.mount: 1}))

    def profile(self, extra=''):
        data = (f'// custom preference preserved\n"libraryfolders"\n{{\n\t"0"\n'
                f'\t{{\n\t\t"path"\t"{self.steam}"\n\t\t"label"\t"Principal"\n'
                f'\t\t"contentid"\t"963"\n\t}}\n{extra}}}\n')
        for path in self.catalogs:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
            path.chmod(0o640)
        return data

    def library(self, relative='SteamLibrary', ident='4242', *, apps=True, mount=None):
        path = (mount or self.mount) / relative
        directory = path / 'steamapps'
        directory.mkdir(parents=True)
        if apps:
            (directory / 'appmanifest_570.acf').write_text('"AppState" { "appid" "570" }')
        if ident is not None:
            (path / 'libraryfolder.vdf').write_text(f'"libraryfolder" {{ "contentid" "{ident}" }}')
        return path

    def recover(self):
        helper.recover(self.home, 'ana')

    def test_prelaunch_contender_waits_for_another_recovery_in_the_same_profile(self):
        self.library()
        arrived = Event()
        entered = Event()

        def second():
            arrived.set()
            self.recover()
            entered.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with helper.recovery_lock(self.steam / 'steamapps'):
                contender = executor.submit(second)
                self.assertTrue(arrived.wait(2))
                self.assertFalse(entered.wait(0.05))
            contender.result(timeout=2)
            self.assertTrue(entered.is_set())
        self.assertIn('/SteamLibrary"', self.catalogs[0].read_text())

    def test_recovers_forgotten_library_in_both_files_and_is_idempotent(self):
        library = self.library()
        self.recover()
        for path in self.catalogs:
            text = path.read_text()
            self.assertIn('// custom preference preserved', text)
            parsed = helper.parse_vdf(text, 'libraryfolders')
            entries = helper.catalog(parsed)
            self.assertEqual([(key, value.data, ident) for key, value, ident in entries],
                             [('0', str(self.steam), '963'), ('1', str(library), '4242')])
            self.assertEqual(parsed.data['0'].data['label'].data, 'Principal')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        snapshots = [(path.read_bytes(), path.stat().st_ino) for path in self.catalogs]
        self.recover()
        self.assertEqual(snapshots, [(path.read_bytes(), path.stat().st_ino) for path in self.catalogs])

    def test_moves_only_the_dangling_matching_path_and_keeps_custom_fields(self):
        old = '/run/media/ana/Jogos antigos/nested/Biblioteca'
        previous = self.profile(f'\t"5" {{ "path" "{old}" "contentid" "4242" '
                                '"label" "Meus jogos" "custom" "keep" "apps" { "570" "8128" } }\n')
        library = self.library('nested/Biblioteca')
        self.recover()
        self.assertEqual(self.catalogs[0].read_text(), previous.replace(old, str(library)))

    def test_never_replaces_an_accessible_registered_path_for_the_same_identity(self):
        library = self.library()
        alias = self.base / 'current-games'
        alias.symlink_to(library, target_is_directory=True)
        previous = self.profile(f'\t"1" {{ "path" "{alias}" "contentid" "4242" }}\n')
        self.recover()
        self.assertEqual(self.catalogs[0].read_text(), previous)

    def test_empty_library_symlink_and_duplicate_disks_are_not_registered(self):
        self.library('empty', apps=False)
        unrelated = self.library(mount=self.base)
        (self.mount / 'symlink').symlink_to(unrelated, target_is_directory=True)
        self.library('one', ident='777')
        self.library('two', ident='777')
        self.recover()
        self.assertEqual(self.catalogs[0].read_text(), self.initial)

    def test_client_in_use_skips_without_creating_lock(self):
        self.library()
        self.running.return_value = True
        self.recover()
        self.assertEqual(self.catalogs[0].read_text(), self.initial)
        self.assertFalse((self.steam / 'steamapps/.callas-libraryfolders.lock').exists())

    def test_client_starting_during_recovery_leaves_files_untouched(self):
        self.library()
        self.running.side_effect = [False, False, True, True]
        self.recover()
        self.assertTrue(all(path.read_text() == self.initial for path in self.catalogs))

    def test_concurrent_edit_and_missing_legacy_copy_are_preserved(self):
        self.library()
        changed = self.initial + '// Steam wrote this after the first read\n'
        self.catalogs[1].unlink()
        reads = 0

        def mount_query(_):
            nonlocal reads
            reads += 1
            if reads == 2:
                self.catalogs[0].write_text(changed)
            return {self.mount: 1}

        self.mounts.side_effect = mount_query
        self.recover()
        self.assertEqual(self.catalogs[0].read_text(), changed)
        self.assertFalse(self.catalogs[1].exists())

    def test_legacy_catalog_and_escaped_new_path_preserve_format(self):
        library = self.library('A "nave"')
        self.catalogs[0].write_text(f'"libraryfolders" {{ "0" "{self.steam}" }}\n')
        self.recover()
        values = helper.parse_vdf(self.catalogs[0].read_text(), 'libraryfolders').data
        self.assertEqual(values['1'].data, str(library))

    def test_missing_or_malformed_client_catalog_is_not_replaced(self):
        self.library()
        self.catalogs[1].unlink()
        self.catalogs[0].write_text('this is not VDF')
        with patch('sys.stderr') as stderr:
            self.recover()
        stderr.write.assert_called()
        self.assertEqual(self.catalogs[0].read_text(), 'this is not VDF')

    def test_device_change_after_scan_does_not_update_catalog(self):
        self.library()
        self.mounts.side_effect = [{self.mount: 1}, {self.mount: 2}]
        self.recover()
        self.assertEqual(self.catalogs[0].read_text(), self.initial)


class MountTests(unittest.TestCase):
    def test_zombie_processes_do_not_count_as_a_running_client(self):
        with patch.object(helper.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as run:
            self.assertFalse(helper.steam_running())
        command = run.call_args.args[0]
        states = command[command.index('--runstates') + 1].split(',')
        self.assertIn('D', states)
        self.assertIn('S', states)
        self.assertNotIn('Z', states)

    def test_only_same_persistent_active_mount_is_eligible(self):
        def entry(source, target, options='rw', fs='ext4'):
            return {'source': source, 'target': target, 'options': options, 'fstype': fs}

        fstab = [
            entry('/dev/by-uuid/a', '/mnt/nvme'),
            entry('/dev/sdb2', '/mnt/different'),
            entry('/dev/sdb2', '/mnt/disabled', 'rw,noauto'),
            entry('/dev/sdb2', '/run/media/other/Jogos'),
            entry('/dev/sdb2', '/'),
            entry('/dev/sdb2', '/mnt/readonly', 'rw'),
            entry('/dev/sdb2', '/mnt/stacked'),
            entry('/dev/sdb2', '/mnt/stacked'),
            entry('/dev/sdc3', '/mnt/overlay'),
            entry('/dev/sda4', '/mnt/system-copy'),
        ]
        mounted = [
            entry('/dev/nvme0n1p1', '/mnt/nvme'),
            entry('/dev/sda2', '/mnt/different'),
            entry('/dev/sdb2', '/mnt/disabled'),
            entry('/dev/sdb2', '/mnt/runtime-only'),
            entry('/dev/sdb2', '/run/media/other/Jogos'),
            entry('/dev/sdb2', '/'),
            entry('/dev/sdb2', '/mnt/readonly', 'ro'),
            entry('/dev/sdb2', '/mnt/stacked'),
            entry('/dev/sdc3', '/mnt/overlay'),
            entry('tmpfs', '/mnt/overlay', fs='tmpfs'),
            entry('/dev/sda4', '/home'),
            entry('/dev/sda4', '/mnt/system-copy'),
        ]
        devices = {'/dev/by-uuid/a': 1, '/dev/nvme0n1p1': 1, '/dev/sdb2': 2, '/dev/sda2': 3,
                   '/dev/sdc3': 4, '/dev/sda4': 5}
        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            if os.fspath(path) in devices:
                return SimpleNamespace(st_rdev=devices[os.fspath(path)], st_mode=stat.S_IFBLK)
            return real_stat(path, *args, **kwargs)

        with patch.object(helper.subprocess, 'run', side_effect=[
                SimpleNamespace(stdout=json.dumps({'filesystems': fstab})),
                SimpleNamespace(stdout=json.dumps({'filesystems': mounted})),
        ]), patch.object(helper.os, 'stat', side_effect=fake_stat):
            self.assertEqual(helper.find_mounts('ana'), {Path('/mnt/nvme'): 1})


if __name__ == '__main__':
    unittest.main()
