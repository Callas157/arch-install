"""Application reconciliation with simulated package managers; no host mutations."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import types
import unittest
from unittest.mock import patch

UP = Path(__file__).resolve().parents[1] / 'atualizador'


def load():
    spec = importlib.util.spec_from_file_location('catalog_test', UP / 'callas-apps.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.apps = load()

    def entry(self, name, state='present', source='repo', phase='apps', **extra):
        return dict(name=name, state=state, source=source, phase=phase, **extra)

    def test_gnome_disks_is_installed_and_offered_by_both_flows(self):
        """GNOME Disks is installed by the shared catalog without a second installer list."""
        entries = self.apps.catalog()
        matches = [entry for entry in entries if entry['name'] == 'gnome-disk-utility']
        self.assertEqual(matches, [self.entry('gnome-disk-utility')])

        catalog_data = json.loads((UP / 'callas-apps.json').read_text())
        defaults = [entry for entry in catalog_data['defaults']
                    if entry['name'] == 'gnome-disk-utility']
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0]['source'], 'repo')
        self.assertEqual(defaults[0]['icon'], 'org.gnome.DiskUtility')

        with patch.object(self.apps, 'removed_choices', return_value=set()):
            pending = self.apps.plan(matches, {'native': {}, 'flatpak': {}}, [])
            self.assertEqual([(item['action'], item['name']) for item in pending],
                             [('install', 'gnome-disk-utility')])
            self.assertEqual(self.apps.plan(matches,
                             {'native': {'gnome-disk-utility': '46.1-3'}, 'flatpak': {}}, []), [])

        security = (UP / 'callas-security.sh').read_text()
        update = (UP / 'callas-config-update.sh').read_text()
        self.assertIn('callas-apps.py\" --apply apps \"$usuario\"', security)
        self.assertIn('callas-apps.py\" --apply apps \"$usuario\"', update)
        self.assertIn('[[ ${2:-} == --installation ]]', security)

    def test_missing_present_retired_and_removed_from_catalog(self):
        entries = [self.entry('haruna'), self.entry('gpu-screen-recorder-gtk', 'absent')]
        installed = {'native': {'gpu-screen-recorder-gtk': '1', 'old-app': '1', 'personal-app': '1'}, 'flatpak': {}}
        previous = [self.entry('old-app')]
        actions = self.apps.plan(entries, installed, previous)
        self.assertEqual([(a['action'], a['name']) for a in actions],
                         [('install', 'haruna'), ('remove', 'gpu-screen-recorder-gtk'), ('remove', 'old-app')])
        self.assertNotIn('personal-app', str(actions))
        self.assertEqual(self.apps.plan([self.entry('haruna')], {'native': {'haruna': '2'}, 'flatpak': {}}, []), [])

    def test_replacement_removal_waits_for_successful_install_and_rechecks(self):
        entries = [self.entry('new-ui'), self.entry('old-ui', 'absent', replacement='new-ui')]
        installed = {'native': {'old-ui': '1'}, 'flatpak': {}}
        with tempfile.TemporaryDirectory() as temp, patch.object(self.apps, 'STATE', Path(temp)), \
                patch.object(self.apps, 'catalog', return_value=entries), \
                patch.object(self.apps, 'inventory', return_value=installed), \
                patch.object(self.apps, 'install', side_effect=RuntimeError('failed')), \
                patch.object(self.apps, 'remove') as remove:
            with self.assertRaises(RuntimeError):
                self.apps.apply('apps', 'fixture')
            remove.assert_not_called()
            self.assertFalse(list(Path(temp).glob('*')))

    def test_active_app_blocks_removal_and_failed_remove_does_not_write_receipt(self):
        entries = [self.entry('old-ui', 'absent')]
        installed = {'native': {'old-ui': '1'}, 'flatpak': {}}
        with tempfile.TemporaryDirectory() as temp, patch.object(self.apps, 'STATE', Path(temp)), \
                patch.object(self.apps, 'catalog', return_value=entries), \
                patch.object(self.apps, 'inventory', return_value=installed), \
                patch.object(self.apps, 'remove', side_effect=RuntimeError('em uso')):
            with self.assertRaises(RuntimeError):
                self.apps.apply('apps', 'fixture')
            self.assertFalse(list(Path(temp).glob('*')))

    def test_successful_apply_is_idempotent_and_records_ownership(self):
        entries = [self.entry('haruna')]
        installed = {'native': {}, 'flatpak': {}}
        def install(entry, user):
            installed['native'][entry['name']] = '1'
        with tempfile.TemporaryDirectory() as temp, patch.object(self.apps, 'STATE', Path(temp)), \
                patch.object(self.apps, 'catalog', return_value=entries), \
                patch.object(self.apps, 'inventory', return_value=installed), \
                patch.object(self.apps, 'install', side_effect=install) as install_mock:
            self.apps.apply('apps', 'fixture')
            self.apps.apply('apps', 'fixture')
            install_mock.assert_called_once()
            self.assertEqual(self.apps.previous('apps'), entries)

    def test_partial_success_keeps_ownership_for_next_release(self):
        entries = [self.entry('new-ui'), self.entry('old-ui', 'absent')]
        installed = {'native': {'old-ui': '1'}, 'flatpak': {}}
        def install(entry, user):
            installed['native'][entry['name']] = '1'
        with tempfile.TemporaryDirectory() as temp, patch.object(self.apps, 'STATE', Path(temp)), \
                patch.object(self.apps, 'catalog', return_value=entries), \
                patch.object(self.apps, 'inventory', return_value=installed), \
                patch.object(self.apps, 'install', side_effect=install), \
                patch.object(self.apps, 'remove', side_effect=RuntimeError('em uso')):
            with self.assertRaises(RuntimeError):
                self.apps.apply('apps', 'fixture')
            managed = self.apps.previous('apps')
            self.assertEqual([e['name'] for e in managed], ['new-ui'])
            self.assertEqual(self.apps.plan([], installed, managed)[0]['name'], 'new-ui')

    def test_process_check_preserves_capture_engine_and_detects_gtk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            process = root / '123'; process.mkdir()
            (process / 'exe').symlink_to('/usr/bin/gpu-screen-recorder')
            (process / 'cmdline').write_bytes(b'gpu-screen-recorder\0-w\0screen\0')
            with patch.object(self.apps, 'command', return_value='/usr/bin/gpu-screen-recorder-gtk\n'):
                self.assertFalse(self.apps.active_native('gpu-screen-recorder-gtk', root))
                (process / 'exe').unlink()
                (process / 'exe').symlink_to('/usr/bin/gpu-screen-recorder-gtk')
                self.assertTrue(self.apps.active_native('gpu-screen-recorder-gtk', root))
                with patch.object(self.apps, 'active_native', return_value=True), \
                        patch.object(self.apps, 'native') as native_mock:
                    with self.assertRaisesRegex(RuntimeError, 'em uso'):
                        self.apps.remove(self.entry('gpu-screen-recorder-gtk', 'absent'), 'fixture')
                    native_mock.assert_not_called()

    def test_inventory_errors_propagate_instead_of_looking_like_empty_machine(self):
        with patch.object(self.apps, 'command', side_effect=RuntimeError('database')):
            with self.assertRaisesRegex(RuntimeError, 'database'):
                self.apps.inventory()

    def test_shared_installer_and_update_stage_catalog_from_same_release(self):
        installer = (UP.parent.parent / 'instalar-arch.sh').read_text()
        security = (UP / 'callas-security.sh').read_text()
        release = (UP / 'callas-release.py').read_text()
        update = (UP / 'callas-config-update.sh').read_text()
        self.assertIn('module.stage_files(sys.argv[1], sys.argv[2], progress=False)', installer)
        for name in ('callas-apps.py', 'callas-apps.json'):
            self.assertIn('programas-callas-os/atualizador/' + name, release)
            self.assertIn(name, security)
        self.assertIn('--apply apps', security)
        self.assertIn('--apply flatpaks', security)
        self.assertLess(update.index('callas-apps.py" --scan'), update.index('for phase in security apps'))

    def test_checkpoint_detects_missing_apps_even_with_same_release_and_matching_receipt(self):
        spec = importlib.util.spec_from_file_location('catalog_state_test', UP / 'callas-update-state.py')
        state = importlib.util.module_from_spec(spec); spec.loader.exec_module(state)
        desired = {'installed': {'native:haruna': '1'}, 'pending': []}
        drift = {'installed': {'native:haruna': None}, 'pending': [{'action': 'install', 'name': 'haruna'}]}
        with tempfile.TemporaryDirectory() as temp, patch.object(state, 'STATE', Path(temp)), \
                patch.object(state, 'fingerprint', return_value='same-release'), \
                patch.object(state, 'REQUIRED', {'apps': ()}), \
                patch.object(state, 'DEPENDENCIES', {'apps': ()}), \
                patch.object(state, 'application_status', return_value=desired) as observation:
            import pwd, os
            user = pwd.getpwuid(os.getuid()).pw_name
            state.complete('apps', Path(temp), user)
            self.assertTrue(state.intact(user))
            self.assertFalse(state.needed('apps', Path(temp), user))
            observation.return_value = drift
            self.assertFalse(state.intact(user))
            self.assertTrue(state.needed('apps', Path(temp), user))
            # A receipt containing a pending result must never enable the fast exit.
            state.complete('apps', Path(temp), user)
            self.assertFalse(state.intact(user))
            self.assertTrue(state.needed('apps', Path(temp), user))

    def test_invalid_duplicate_or_protected_package_rejected_before_commands(self):
        for entries in ([self.entry('linux')], [self.entry('mesa')], [self.entry('--bad')],
                        [self.entry('haruna'), self.entry('haruna', 'absent')],
                        [self.entry('haruna', state='unknown')]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.apps.validate({'schema': 1, 'applications': entries})

    def test_scan_reads_gpu_vendors_without_selecting_drivers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cpu = root / 'cpuinfo'; cpu.write_text('vendor_id : AuthenticAMD\n')
            pci = root / 'pci'; pci.mkdir()
            for index, vendor in enumerate(('0x10de', '0x1002', '0x8086')):
                device = pci / str(index); device.mkdir()
                (device / 'class').write_text('0x030000\n')
                (device / 'vendor').write_text(vendor)
            result = self.apps.hardware(cpu, pci)
            self.assertEqual(result, {'cpu': ['AMD'], 'gpu': ['AMD', 'Intel', 'NVIDIA']})

    def test_flatpak_removal_checks_desktop_users_and_preserves_user_data(self):
        for busy in (True, False):
            calls = []
            def command(argv):
                calls.append(argv)
                return 'com.example.Retired\n' if busy and argv[0].endswith('runuser') else ''
            account = types.SimpleNamespace(pw_dir='/home/fixture', pw_uid=1000)
            with self.subTest(busy=busy), patch.object(self.apps, 'command', side_effect=command), \
                    patch.object(self.apps.pwd, 'getpwnam', return_value=account):
                entry = self.entry('com.example.Retired', 'absent', 'flatpak', 'flatpaks')
                if busy:
                    with self.assertRaisesRegex(RuntimeError, 'em uso'):
                        self.apps.remove(entry, 'fixture')
                else:
                    self.apps.remove(entry, 'fixture')
                queries = [args for args in calls if args[0].endswith('runuser')]
                self.assertTrue(queries)
                self.assertIn('XDG_RUNTIME_DIR=/run/user/1000', queries[0])
                removals = [args for args in calls if args[0] == 'flatpak']
                self.assertEqual(bool(removals), not busy)
                if removals:
                    self.assertEqual(removals[0], ['flatpak', 'uninstall', '--system', '--noninteractive', '--assumeyes', 'com.example.Retired'])
                self.assertNotIn('--delete-data', str(calls))

    def test_resolved_removal_guard_rejects_protected_targets(self):
        native = self.apps.native()
        for target in ('old-ui', 'linux', 'nvidia-utils', 'mesa'):
            def runner(argv):
                hooks = Path(argv[argv.index('--hookdir', argv.index('--hookdir') + 1) + 1])
                hook = next(hooks.glob('*.hook')).read_text()
                guard = hook.split('Exec = /usr/bin/python3 ', 1)[1].strip()
                return subprocess.run(['python', guard], input=target+'\n', text=True, capture_output=True)
            with self.subTest(target=target):
                result = native.guarded_transaction(['-R', '--noconfirm', 'old-ui'], runner=runner)
                self.assertEqual(result.returncode == 0, target == 'old-ui')

    def test_transaction_removal_is_exact_and_guarded(self):
        native = self.apps.native()
        with self.assertRaises(ValueError):
            native.guarded_transaction(['-R', '-s', 'old-ui'])
        seen = []
        def runner(command):
            seen.append(command)
            hookdir = Path(command[command.index('--hookdir', command.index('--hookdir') + 1) + 1])
            self.assertIn('Operation = Remove', next(hookdir.glob('*.hook')).read_text())
        native.guarded_transaction(['-R', '--noconfirm', 'old-ui'], runner=runner)
        self.assertEqual(seen[0][-3:], ['-R', '--noconfirm', 'old-ui'])


if __name__ == '__main__':
    unittest.main()
