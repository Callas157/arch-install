"""Offline battery deployment. No real packages, root writes or session restart."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'baterias'
spec = importlib.util.spec_from_file_location('battery_install', SOURCE / 'callas-baterias-install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class BatteryDeploymentTests(unittest.TestCase):
    def test_matching_installation_is_preserved_and_missing_or_changed_files_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); system = root / 'system'; home = root / 'home'
            archive = SOURCE / 'callas-baterias.tar.gz'
            installer.deploy(archive, system)
            installer.configure_user(home, system)
            self.assertTrue(installer.current(archive, home, system))
            override = home / '.config/autostart/callas-baterias.desktop'
            override.write_text(installer.DESKTOP + 'Hidden=true\n')
            self.assertTrue(installer.current(archive, home, system))
            target = system / installer.APP.relative_to('/') / 'sharktray/mouse.py'
            target.write_text('outdated')
            self.assertFalse(installer.current(archive, home, system))
            installer.deploy(archive, system)
            self.assertTrue(installer.current(archive, home, system))
            target.unlink()
            self.assertFalse(installer.current(archive, home, system))

    def test_unchanged_install_does_not_redeploy_or_restart(self):
        from types import SimpleNamespace
        account = SimpleNamespace(pw_uid=1000, pw_dir='/home/fixture')
        with patch.object(installer.pwd, 'getpwnam', return_value=account), \
             patch.object(installer.os, 'geteuid', return_value=0), \
             patch.object(installer, 'ensure_dependencies'), \
             patch.object(installer, 'differences', return_value=[]), \
             patch.object(installer, 'deploy') as deploy, \
             patch.object(installer.subprocess, 'run') as run:
            installer.install_system('fixture', SOURCE / 'callas-baterias.tar.gz')
            deploy.assert_not_called()
            run.assert_not_called()

    def test_installer_only_change_does_not_reinstall_identical_payload(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / 'system'; home = Path(tmp) / 'home'
            archive = SOURCE / 'callas-baterias.tar.gz'
            installer.deploy(archive, system)
            installer.configure_user(home, system)
            helper = system / installer.SELF.lstrip('/')
            helper.write_text('# previous installer version\n')
            app = system / installer.APP.relative_to('/') / 'callas_baterias.py'
            before = app.stat().st_mtime_ns
            account = SimpleNamespace(pw_uid=1000, pw_dir=str(home))
            with patch.object(installer.pwd, 'getpwnam', return_value=account), \
                 patch.object(installer.os, 'geteuid', return_value=0), \
                 patch.object(installer, 'ensure_dependencies'), \
                 patch.object(installer.subprocess, 'run') as run:
                installer.install_system('fixture', archive, system=system)
                run.assert_not_called()
            self.assertEqual(app.stat().st_mtime_ns, before)
            self.assertEqual(helper.read_bytes(), Path(installer.__file__).read_bytes())

    def test_shortcut_repair_does_not_touch_app_or_restart_service(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / 'system'; home = Path(tmp) / 'home'
            archive = SOURCE / 'callas-baterias.tar.gz'
            installer.deploy(archive, system)
            installer.configure_user(home, system)
            shortcut = system / 'usr/local/share/applications/callas-baterias.desktop'
            shortcut.unlink()
            app = system / installer.APP.relative_to('/') / 'callas_baterias.py'
            before = app.stat().st_mtime_ns
            account = SimpleNamespace(pw_uid=1000, pw_dir=str(home))
            with patch.object(installer.pwd, 'getpwnam', return_value=account), \
                 patch.object(installer.os, 'geteuid', return_value=0), \
                 patch.object(installer, 'ensure_dependencies'), \
                 patch.object(installer.subprocess, 'run') as run:
                installer.install_system('fixture', archive, system=system)
                run.assert_not_called()
            self.assertEqual(shortcut.read_text(), installer.DESKTOP)
            self.assertEqual(app.stat().st_mtime_ns, before)

    def test_changed_runtime_restarts_service_and_keeps_udev_untouched(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / 'system'; home = Path(tmp) / 'home'
            archive = SOURCE / 'callas-baterias.tar.gz'
            installer.deploy(archive, system)
            installer.configure_user(home, system)
            app = system / installer.APP.relative_to('/') / 'callas_baterias.py'
            app.write_text('# outdated runtime\n')
            account = SimpleNamespace(pw_uid=1000, pw_dir=str(home))
            original_exists = Path.exists
            def exists(path):
                return True if str(path) == '/run/user/1000/bus' else original_exists(path)
            with patch.object(installer.pwd, 'getpwnam', return_value=account), \
                 patch.object(installer.os, 'geteuid', return_value=0), \
                 patch.object(installer, 'ensure_dependencies'), \
                 patch.object(Path, 'exists', exists), \
                 patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                installer.install_system('fixture', archive, system=system)
            calls = [call.args[0] for call in run.call_args_list]
            self.assertTrue(any(command[-2:] == ['restart', 'callas-baterias.service'] for command in calls))
            self.assertFalse(any(command[0] == 'udevadm' for command in calls))
            self.assertEqual(app.read_bytes(), (SOURCE / 'app/callas_baterias.py').read_bytes())

    def test_repeat_deployment_preserves_unchanged_file_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / 'system'; home = Path(tmp) / 'home'
            archive = SOURCE / 'callas-baterias.tar.gz'
            installer.deploy(archive, system)
            installer.configure_user(home, system)
            files = [p for base in (system, home) for p in base.rglob('*') if p.is_file()]
            before = {p: p.stat().st_mtime_ns for p in files}
            installer.deploy(archive, system)
            installer.configure_user(home, system)
            self.assertEqual(before, {p: p.stat().st_mtime_ns for p in files})

    def test_dependencies_use_only_guarded_target_and_propagate_failure(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if args[0] == 'pacman': return subprocess.CompletedProcess(args, 1)
            raise subprocess.CalledProcessError(1, args)
        with patch.object(installer.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError): installer.ensure_dependencies()
        self.assertEqual(calls[-1], ['/usr/local/libexec/callas-native', '--install', 'pyside6'])

    def test_installed_dependency_does_not_start_transaction(self):
        with patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            installer.ensure_dependencies()
        self.assertEqual(run.call_count, 1)

    def test_global_files_and_existing_user_override_are_replaced_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / 'system'; home = Path(tmp) / 'home'
            installer.deploy(SOURCE / 'callas-baterias.tar.gz', system)
            existing = home / '.config/systemd/user/callas-baterias.service'
            existing.parent.mkdir(parents=True); existing.write_text('old local path')
            installer.configure_user(home, system)
            unit = existing.read_text()
            self.assertIn('/usr/local/share/callas-os/baterias/callas_baterias.py', unit)
            self.assertTrue((home / '.config/autostart/callas-baterias.desktop').is_file())
            self.assertTrue((home / '.local/share/plasma/plasmoids/br.com.callas.ordem-baterias/metadata.json').is_file())
            self.assertEqual((system / 'etc/udev/rules.d/71-callas-baterias.rules').stat().st_mode & 0o777, 0o644)
            for path in ('callas_baterias.py', 'sharktray/mouse.py'):
                self.assertEqual((system / 'usr/local/share/callas-os/baterias' / path).read_bytes(), (SOURCE / 'app' / path).read_bytes())
            # Updating twice preserves appearance/preferences and disables duplicate old icons.
            prefs = home / '.config/sharktray-test.ini'; prefs.write_text('custom appearance')
            installer.configure_user(home, system)
            self.assertEqual(prefs.read_text(), 'custom appearance')
            self.assertIn('Hidden=true', (home / '.config/autostart/attackshark-tray.desktop').read_text())

    def test_unsafe_archive_is_rejected_before_global_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); archive = p / 'bad.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                entry = tarfile.TarInfo('../escape'); entry.size = 1
                tar.addfile(entry, io.BytesIO(b'x'))
            with self.assertRaises(ValueError): installer.deploy(archive, p / 'system')
            self.assertFalse((p / 'system').exists())

    def test_payload_matches_every_canonical_source(self):
        with tarfile.open(SOURCE / 'callas-baterias.tar.gz', 'r:gz') as tar:
            packaged = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
        expected = {str(p.relative_to(SOURCE)): p.read_bytes() for folder in ('app', 'painel')
                    for p in (SOURCE / folder).rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(packaged, expected)

    def test_both_shared_modes_execute_the_same_battery_deployer(self):
        source = (ROOT / 'atualizador/callas-security.sh').read_text()
        block = source.split('  # Shared by clean-install --installation and option 5 --config-update.\n')[1].split('\n  /usr/local/libexec/callas-game-logs --install-system', 1)[0]
        for mode in ('--installation', '--config-update'):
            result = subprocess.run(['bash', '-c', 'set -eu\nstage=/verified\nusuario=fixture\npython(){ printf "%s\\n" "$@"; }\n' + block, 'test', 'fixture', mode], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ['/verified/callas-baterias-install.py', '--install-system', 'fixture', '--payload', '/verified/callas-baterias.tar.gz'])

    def test_x6_capture_is_100_percent_and_original_variant_is_unchanged(self):
        if importlib.util.find_spec('PySide6') is None: self.skipTest('PySide6 unavailable')
        code = '''import tempfile
from pathlib import Path
from PySide6.QtCore import QCoreApplication
import sharktray.mouse as m
app=QCoreApplication([])
with tempfile.TemporaryDirectory() as temp:
 m.LEVEL_FILE=Path(temp)/'level.json'
 monitor=m.MouseMonitor(); monitor._watch.stop(); monitor._close()
 for frame,expected in [('03 10 40 02 0a',100),('03 10 40 03 09',90),('03 e5 40 01 64',100)]:
  assert monitor._accept(bytes.fromhex(frame))
  assert monitor._level==expected,(frame,monitor._level)
 assert not monitor._accept(bytes.fromhex('03 10 40 02 0b'))
 assert not monitor._accept(bytes.fromhex('03 e5 01 00 00'))
'''
        result = subprocess.run(['python3', '-c', code], cwd=SOURCE / 'app', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_absent_kde_session_does_not_fail_the_app(self):
        with patch.object(installer.shutil, 'which', return_value='/usr/bin/qdbus6'), \
             patch.object(installer.subprocess, 'run', side_effect=subprocess.TimeoutExpired('qdbus6', 1)), \
             patch.object(installer.time, 'sleep'):
            installer.arrange_tray()

    def test_root_deployment_is_readable_under_security_umask(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / 'system'
            previous = os.umask(0o077)
            try: installer.deploy(SOURCE / 'callas-baterias.tar.gz', system)
            finally: os.umask(previous)
            for directory in ('usr/local/share/callas-os', 'usr/local/share/callas-os/baterias',
                              'usr/local/share/plasma', 'usr/local/share/plasma/plasmoids',
                              'usr/local/share/plasma/plasmoids/br.com.callas.ordem-baterias',
                              'etc/xdg/autostart', 'etc/systemd/user'):
                self.assertEqual((system / directory).stat().st_mode & 0o777, 0o755, directory)

    def test_disabled_autostart_survives_user_reconfiguration(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / 'system'; home = Path(tmp) / 'home'
            installer.deploy(SOURCE / 'callas-baterias.tar.gz', system)
            path = home / '.config/autostart/callas-baterias.desktop'
            path.parent.mkdir(parents=True)
            path.write_text('[Desktop Entry]\nHidden=true\n')
            installer.configure_user(home, system)
            self.assertIn('Hidden=true', path.read_text())

    def test_disabling_autostart_creates_override_for_global_entry(self):
        if importlib.util.find_spec('PySide6') is None: self.skipTest('PySide6 unavailable')
        code = '''from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
from callas_baterias import UnifiedTray
obj=SimpleNamespace()
obj.autostart_enabled=lambda:UnifiedTray.autostart_enabled(obj)
with TemporaryDirectory() as tmp, patch.object(Path,'home',return_value=Path(tmp)):
 assert UnifiedTray.set_autostart(obj,False) is False
 p=Path(tmp)/'.config/autostart/callas-baterias.desktop'
 assert p.is_file() and 'Hidden=true' in p.read_text()
 assert UnifiedTray.set_autostart(obj,True) is True
'''
        result = subprocess.run(['python3', '-c', code], cwd=SOURCE / 'app', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
