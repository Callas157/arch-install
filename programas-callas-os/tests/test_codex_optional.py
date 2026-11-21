"""Optional Codex install: user profile, integrity, cancellation and no auto-install."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('codex_central', ROOT/'atualizador/callas-update-gui.py')
gui = importlib.util.module_from_spec(spec); spec.loader.exec_module(gui)
from PySide6.QtWidgets import QApplication
APP = QApplication.instance() or QApplication([])


def bundle(name='installer.py', content=b'print("fixture")'):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        info = tarfile.TarInfo(name); info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class OptionalCodexTests(unittest.TestCase):
    def test_home_has_icon_button_without_downloading_or_installing(self):
        with patch.object(gui.urllib.request, 'urlopen') as download, patch.object(gui.subprocess, 'Popen') as process:
            window = gui.Window()
            button = next(b for b in window.buttons if b.text() == 'Codex')
            self.assertFalse(button.icon().isNull())
            download.assert_not_called(); process.assert_not_called()
            window.close(); window.deleteLater()
        release = (ROOT/'atualizador/callas-release.py').read_text().split('FILES = (', 1)[1].split('\n)', 1)[0]
        self.assertNotIn('codex.tar.gz', release)

    def test_existing_app_opens_without_sudo_or_install(self):
        window = gui.Window()
        with tempfile.TemporaryDirectory() as folder:
            launcher = Path(folder)/'app'; launcher.write_text('#!/bin/sh\nexit 0'); launcher.chmod(0o755)
            with patch.object(gui, 'codex_launcher', return_value=launcher), \
                 patch.object(gui.subprocess, 'Popen') as process, patch.object(window, 'start') as start:
                window.codex()
                self.assertEqual(process.call_args.args[0], [str(launcher)])
                start.assert_not_called()
        window.close(); window.deleteLater()

    def test_cancel_and_confirm_optional_install(self):
        window = gui.Window()
        with patch.object(gui, 'codex_launcher', return_value=Path('/nonexistent/codex')), \
             patch.object(window, 'start') as start:
            window.codex(); window.confirm_cancel.click()
            start.assert_not_called()
            window.codex(); window.confirm_yes.click()
            start.assert_called_once_with('codex')
        window.close(); window.deleteLater()

    def test_user_process_preserves_askpass_and_drops_general_context(self):
        window = gui.Window()
        original = subprocess.Popen
        invoked = []
        def process(args, **kwargs):
            invoked.append((args, kwargs['env']))
            return original(['/usr/bin/python3', '-c', 'print("fixture done")'], **kwargs)
        with patch.object(gui, 'package_state', return_value={}), \
             patch.object(gui.subprocess, 'Popen', side_effect=process), \
             patch.dict(os.environ, {'CALLAS_KERNEL_UPDATE_CONTEXT': 'general'}):
            window.start('codex')
            deadline = time.monotonic() + 5
            while window.process is not None and time.monotonic() < deadline:
                APP.processEvents(); time.sleep(.01)
        self.assertIsNone(window.process)
        args, env = invoked[0]
        self.assertEqual(args, gui.action_command('codex'))
        self.assertNotIn('/usr/bin/sudo', args)
        self.assertNotIn('CALLAS_KERNEL_UPDATE_CONTEXT', env)
        self.assertIn('SUDO_ASKPASS', env)
        self.assertIn('Codex instalado', window.status.text())
        self.assertFalse(window.reboot_pending)
        window.close(); window.deleteLater()

    def download_fixture(self, data):
        response = io.BytesIO(data); response.url = 'https://raw.githubusercontent.com/fixture'
        return patch.object(gui.urllib.request, 'urlopen', return_value=response)

    def test_integrity_failure_never_executes_package(self):
        with self.download_fixture(b'corrupted'), patch.object(gui.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'não corresponde'): gui.install_codex()
            run.assert_not_called()

    def test_unsafe_archive_is_rejected_before_execution(self):
        data = bundle('../escape')
        with self.download_fixture(data), patch.object(gui, 'CODEX_SHA256', hashlib.sha256(data).hexdigest()), \
             patch.object(gui.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'inválido'): gui.install_codex()
            run.assert_not_called()

    def test_valid_download_runs_installer_as_user(self):
        data = bundle()
        with self.download_fixture(data), patch.object(gui, 'CODEX_SHA256', hashlib.sha256(data).hexdigest()), \
             patch.object(gui, 'apply_codex_overlay') as overlay, \
             patch.object(gui.subprocess, 'run') as run:
            gui.install_codex()
            overlay.assert_called_once()
            self.assertEqual(run.call_count, 1)
            args = run.call_args.args[0]
            self.assertEqual(args[:2], ['/usr/bin/python3', '-u'])
            self.assertTrue(args[2].endswith('/installer.py'))
            self.assertTrue(run.call_args.kwargs['check'])


    def test_verified_overlay_rejects_changed_source_before_install(self):
        with tempfile.TemporaryDirectory() as folder:
            remote = io.BytesIO(b'código adulterado'); remote.url = 'https://raw.githubusercontent.com/test'
            with patch.object(gui, 'CODEX_OVERLAY', {'callas_chat/ui.py': '0' * 40}), \
                 patch.object(gui.urllib.request, 'urlopen', return_value=remote):
                with self.assertRaisesRegex(ValueError, 'integridade'):
                    gui.apply_codex_overlay(folder)

    def test_old_codex_asks_to_update_newer_stays_untouched(self):
        window = gui.Window()
        with tempfile.TemporaryDirectory() as folder:
            launcher = Path(folder)/'app'
            launcher.write_text('#!/bin/sh\nexit 0\n'); launcher.chmod(0o755)
            with patch.object(gui, 'codex_launcher', return_value=launcher), \
                 patch.object(gui, 'codex_installed_version', return_value=(1, 3, 3)), \
                 patch.object(gui.subprocess, 'Popen') as popen, \
                 patch.object(window, 'start') as start:
                window.codex()
                popen.assert_not_called()
                window.confirm_yes.click()
                start.assert_called_once_with('codex')
            # Versão local mais nova não pode sofrer downgrade.
            with patch.object(gui, 'codex_launcher', return_value=launcher), \
                 patch.object(gui, 'codex_installed_version', return_value=(1, 5, 0)), \
                 patch.object(gui.subprocess, 'Popen') as popen:
                window.codex()
                popen.assert_called_once()
        window.close(); window.deleteLater()


    def test_update_skips_codex_not_installed_even_if_update_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(gui, 'codex_launcher', return_value=Path(folder)/'missing'), \
                 patch.object(gui, 'install_codex') as install, \
                 patch.object(gui.urllib.request, 'urlopen') as download:
                self.assertEqual(gui.auto_update_installed_codex(), 0)
                install.assert_not_called()
                download.assert_not_called()

    def test_update_preserves_unknown_and_newer_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            launcher = Path(folder)/'callas-chat'
            launcher.write_text('#!/bin/sh\\nexit 0\\n')
            launcher.chmod(0o755)
            with patch.object(gui, 'codex_launcher', return_value=launcher), \
                 patch.object(gui, 'install_codex') as install:
                for version in (None, (1, 4, 0), (1, 5, 0)):
                    with patch.object(gui, 'codex_installed_version', return_value=version):
                        self.assertEqual(gui.auto_update_installed_codex(), 0)
                install.assert_not_called()

    def test_update_defers_running_codex_without_closing_or_modifying_it(self):
        with tempfile.TemporaryDirectory() as folder:
            launcher = Path(folder)/'callas-chat'
            launcher.write_text('#!/bin/sh\\nexit 0\\n')
            launcher.chmod(0o755)
            with patch.object(gui, 'codex_launcher', return_value=launcher), \
                 patch.object(gui, 'codex_installed_version', return_value=(1, 3, 3)), \
                 patch.object(gui, 'codex_running_for_user', return_value=True), \
                 patch.object(gui, 'install_codex') as install:
                self.assertEqual(gui.auto_update_installed_codex(), 0)
                install.assert_not_called()

    def test_update_replaces_only_existing_older_app_files(self):
        with tempfile.TemporaryDirectory() as folder:
            launcher = Path(folder)/'callas-chat'
            launcher.write_text('#!/bin/sh\\nexit 0\\n')
            launcher.chmod(0o755)
            with patch.object(gui, 'codex_launcher', return_value=launcher), \
                 patch.object(gui, 'codex_installed_version', side_effect=[(1, 3, 3), (1, 4, 0)]), \
                 patch.object(gui, 'codex_running_for_user', return_value=False), \
                 patch.object(gui, 'install_codex') as install:
                self.assertEqual(gui.auto_update_installed_codex(), 0)
                install.assert_called_once_with(app_only=True)

    def test_app_only_update_skips_whisper_and_package_reinstallation(self):
        data = bundle()
        with self.download_fixture(data), patch.object(gui, 'CODEX_SHA256', hashlib.sha256(data).hexdigest()), \
             patch.object(gui, 'apply_codex_overlay') as overlay, \
             patch.object(gui, 'codex_running_for_user', return_value=False), \
             patch.object(gui.subprocess, 'run') as run:
            gui.install_codex(app_only=True)
            overlay.assert_called_once()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-1], '--sem-dependencias')


    def test_process_opened_during_download_prevents_last_second_install(self):
        data = bundle()
        with self.download_fixture(data), patch.object(gui, 'CODEX_SHA256', hashlib.sha256(data).hexdigest()), \
             patch.object(gui, 'apply_codex_overlay'), \
             patch.object(gui, 'codex_running_for_user', return_value=True), \
             patch.object(gui.subprocess, 'run') as run:
            self.assertFalse(gui.install_codex(app_only=True))
            run.assert_not_called()


if __name__ == '__main__': unittest.main()
