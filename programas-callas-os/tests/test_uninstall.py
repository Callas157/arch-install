"""Uninstaller safety and user choices; package transactions are simulated."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

UP = Path(__file__).resolve().parents[1] / 'atualizador'


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), UP / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UninstallTests(unittest.TestCase):
    def test_system_desktop_and_unknown_tools_are_blocked(self):
        helper = load('callas-uninstall')
        for package in ('linux', 'nvidia-utils', 'plasma-desktop', 'dolphin', 'konsole', 'pyside6'):
            self.assertTrue(helper.blocked_native(package, {'Categories': 'Utility;'}), package)
        self.assertTrue(helper.blocked_native('unknown-tool', {'Categories': 'Settings;System;'}))
        self.assertFalse(helper.blocked_native('spotify', {'Categories': 'AudioVideo;'}))
        self.assertFalse(helper.blocked_native('libreoffice-fresh', {'Categories': 'Office;'}))
        self.assertFalse(helper.blocked_native('gnome-boxes', {'Categories': 'System;Emulator;'}))
        self.assertFalse(helper.blocked_native('qbittorrent', {'Categories': 'Network;FileTransfer;'}))

    def test_catalog_respects_removed_apps_but_keeps_other_migrations(self):
        apps = load('callas-apps')
        with tempfile.TemporaryDirectory() as temp, patch.object(apps, 'STATE', Path(temp)):
            apps.remember_removal('native', 'spotify')
            entries = [dict(name=n, source='repo', phase='apps', state=s) for n, s in
                       [('spotify', 'present'), ('haruna', 'present'), ('old-app', 'absent')]]
            actions = apps.plan(entries, {'native': {'old-app': '1'}, 'flatpak': {}}, [])
            self.assertEqual([(a['name'], a['action']) for a in actions], [('haruna', 'install'), ('old-app', 'remove')])
            # An explicitly reinstalled app is preserved, never removed by the opt-out.
            actions = apps.plan(entries[:1], {'native': {'spotify': '2'}, 'flatpak': {}}, [])
            self.assertEqual(actions, [])

    def test_native_remove_revalidates_and_never_cascades(self):
        helper = load('callas-uninstall')
        app = dict(kind='native', id='spotify', name='Spotify', blocked=False, reason='')
        policy = load('callas-native')
        with patch.object(helper, 'native_apps', return_value=[app]), \
                patch.object(helper, 'active_native', return_value=False), \
                patch.object(helper, 'catalog_module') as catalog, \
                patch.object(helper, 'policy', return_value=policy), \
                patch.object(policy, 'guarded_transaction') as transaction, \
                patch.object(helper, 'native_installed', return_value=False):
            transaction.return_value.returncode = 0
            helper.remove_system('native', 'spotify')
            transaction.assert_called_once_with(['-R', '--noconfirm', 'spotify'])
            catalog.return_value.remember_removal.assert_called_once_with('native', 'spotify')
            app['blocked'] = True
            transaction.reset_mock()
            with self.assertRaises(RuntimeError): helper.remove_system('native', 'spotify')
            transaction.assert_not_called()

    def test_failed_transaction_never_records_success(self):
        helper = load('callas-uninstall')
        app = dict(kind='native', id='spotify', name='Spotify', blocked=False, reason='')
        with patch.object(helper, 'native_apps', return_value=[app]), \
                patch.object(helper, 'active_native', return_value=False), \
                patch.object(helper, 'policy') as policy, patch.object(helper, 'catalog_module') as catalog:
            policy.return_value.guarded_transaction.return_value.returncode = 1
            with self.assertRaises(RuntimeError): helper.remove_system('native', 'spotify')
            catalog.return_value.remember_removal.assert_not_called()

    def test_portable_paths_never_follow_links_or_escape_home(self):
        helper = load('callas-uninstall')
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'home'; home.mkdir()
            apps = home / 'Applications'; apps.mkdir()
            image = apps / 'Example.AppImage'; image.write_text('app')
            self.assertTrue(helper.safe_image(image, home))
            self.assertFalse(helper.safe_image(Path('/usr/bin/bash'), home))
            link = apps / 'linked.AppImage'; link.symlink_to(image)
            self.assertFalse(helper.safe_image(link, home))
            folder = home / 'Downloads'; folder.symlink_to(apps, target_is_directory=True)
            self.assertFalse(helper.safe_image(folder / image.name, home))

    def test_running_native_and_flatpak_are_preserved(self):
        helper = load('callas-uninstall')
        app = dict(kind='native', id='spotify', name='Spotify', blocked=False, reason='')
        with patch.object(helper, 'native_apps', return_value=[app]), \
                patch.object(helper, 'active_native', return_value=True), patch.object(helper, 'policy') as policy:
            with self.assertRaisesRegex(RuntimeError, 'em uso'): helper.remove_system('native', 'spotify')
            policy.assert_not_called()
        ref = 'app/com.example.App/x86_64/stable'; app.update(id=ref)
        with patch.object(helper, 'flatpak_apps', return_value=[app]), \
                patch.object(helper, 'flatpak_active', return_value=True), patch.object(helper, 'command') as run:
            with self.assertRaisesRegex(RuntimeError, 'em uso'): helper.remove_user('flatpak-user', ref)
            run.assert_not_called()

    def test_process_scan_skips_itself_and_tolerates_inaccessible_system_service(self):
        helper = load('callas-uninstall')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            own = root / str(os.getpid()); own.mkdir()
            (own / 'cmdline').write_bytes(b'callas-uninstall\0--remove\0appimage\0/tmp/demo.AppImage\0')
            service = root / str(os.getpid() + 1); service.mkdir()
            (service / 'cmdline').write_bytes(b'/usr/lib/systemd/systemd\0--user\0')
            real_iterdir = Path.iterdir
            real_readlink = os.readlink
            def readlink(path, *args, **kwargs):
                if Path(path) == service / 'exe': raise PermissionError('nondumpable')
                return real_readlink(path, *args, **kwargs)
            with patch.object(helper.Path, 'iterdir', lambda path: iter([own, service]) if str(path) == '/proc' else real_iterdir(path)), \
                    patch.object(helper.os, 'readlink', side_effect=readlink):
                self.assertFalse(helper.user_active(['/tmp/demo.AppImage']))
                (service / 'cmdline').write_bytes(b'python\0-m\0callas_chat\0')
                self.assertTrue(helper.user_active([], modules=('callas_chat',)))

    def test_appimage_icon_comes_from_desktop_without_executing_it(self):
        helper = load('callas-uninstall')
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp); data = home / '.local/share'; entries = data / 'applications'; entries.mkdir(parents=True)
            image = home / 'Example.AppImage'; image.write_text('fixture')
            (entries / 'example.desktop').write_text('[Desktop Entry]\nType=Application\nName=Example\n'
                + 'Exec=' + str(image) + '\nIcon=example-icon\n')
            with patch.object(helper.Path, 'home', return_value=home), patch.object(helper, 'data_home', return_value=data):
                apps = helper.user_apps()
            self.assertEqual([(app['name'], app['icon']) for app in apps], [('Example', 'example-icon')])

    def test_real_cli_appimage_removes_file_not_profile_or_other_files(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp); folder = home / 'Applications'; folder.mkdir()
            image = folder / 'Example.AppImage'; image.write_text('fixture')
            keep = folder / 'keep.txt'; keep.write_text('keep')
            profile = home / '.config/example'; profile.mkdir(parents=True)
            (profile / 'preferences').write_text('preserve')
            result = subprocess.run(['/usr/bin/python3', str(UP / 'callas-uninstall.py'), '--remove',
                                     'appimage', str(image)], capture_output=True, text=True,
                                    env=dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / '.local/share')))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(image.exists())
            self.assertEqual(keep.read_text(), 'keep')
            self.assertEqual((profile / 'preferences').read_text(), 'preserve')

    def test_codex_removal_preserves_conversations_and_attachments(self):
        helper = load('callas-uninstall')
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp); data = home / '.local/share'; base = data / 'callas-chat'
            for name in ('app', 'app.previous', 'venv', 'runtime', 'attachments', 'models'):
                (base / name).mkdir(parents=True)
                (base / name / 'fixture').write_text(name)
            executable = home / '.local/bin/callas-chat'; executable.parent.mkdir(parents=True)
            executable.write_text('fixture')
            auth = home / '.codex/auth.json'; auth.parent.mkdir(); auth.write_text('private')
            with patch.object(helper.Path, 'home', return_value=home), \
                    patch.object(helper, 'data_home', return_value=data), \
                    patch.object(helper, 'user_active', return_value=False), \
                    patch.object(helper, 'refresh_menu'):
                helper.remove_user('codex', 'callas-chat')
            self.assertFalse(executable.exists()); self.assertFalse((base / 'app').exists())
            self.assertEqual(auth.read_text(), 'private')
            self.assertEqual((base / 'attachments/fixture').read_text(), 'attachments')
            self.assertEqual((base / 'models/fixture').read_text(), 'models')

    def test_flatpak_uses_exact_application_ref_and_preserves_data(self):
        helper = load('callas-uninstall')
        ref = 'app/io.missioncenter.MissionCenter/x86_64/stable'
        app = dict(kind='flatpak-system', id=ref, name='Mission Center', blocked=False, reason='')
        with patch.object(helper, 'flatpak_apps', side_effect=[[app], []]), \
                patch.object(helper, 'flatpak_active', return_value=False), \
                patch.object(helper, 'command', return_value='') as command, \
                patch.object(helper, 'catalog_module') as catalog:
            helper.remove_system('flatpak-system', ref)
            self.assertIn(['/usr/bin/flatpak', 'uninstall', '--system', '--noninteractive', '--assumeyes', ref],
                          [c.args[0] for c in command.call_args_list])
            catalog.return_value.remember_removal.assert_called_once_with('flatpak', 'io.missioncenter.MissionCenter')
            self.assertNotIn('--delete-data', str(command.call_args_list))

if __name__ == '__main__': unittest.main()
