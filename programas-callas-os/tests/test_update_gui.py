import importlib.util
import os
from pathlib import Path
import tempfile
import time
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'atualizador' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
gui = load('callas-update-gui')
installer = load('callas-update-gui-install')
from PySide6.QtWidgets import QApplication
APP = QApplication.instance() or QApplication([])

class UpdaterGuiTests(unittest.TestCase):
    def test_monitor_controls_are_between_title_and_explanation_and_grouped_at_top(self):
        with patch.object(gui.MonitorDialog, 'detect'):
            dialog = gui.MonitorDialog()
        dialog.detected(0, '[{"name":"DP-1","priority":1},{"name":"HDMI-1","priority":2}]', '')
        dialog.resize(894, 786); dialog.show(); APP.processEvents()
        title = dialog.findChild(gui.QLabel, 'stage')
        first = dialog.choices.itemAt(0).widget()
        last = dialog.choices.itemAt(1).widget()
        self.assertLess(title.geometry().bottom(), first.geometry().top())
        self.assertLess(last.geometry().bottom(), dialog.message.geometry().top())
        self.assertLess(first.geometry().top() - title.geometry().bottom(), 30)
        self.assertLess(dialog.message.geometry().top() - last.geometry().bottom(), 30)
        dialog.close(); dialog.deleteLater()

    def test_real_progress_and_unknown_totals(self):
        self.assertEqual(gui.progress_state('downloading package 45%'), ('Baixando atualizações', 45))
        self.assertEqual(gui.progress_state('installing package'), ('Instalando atualizações', None))
        self.assertEqual(gui.progress_state('==> Kernels padrão/LTS, DKMS e boot'), ('Kernels padrão/LTS, DKMS e boot', None))
        self.assertIsNone(gui.progress_state('pacote com versão 2026')[1])

    def test_reboot_only_on_change_or_marker(self):
        self.assertFalse(gui.reboot_needed({'linux': '1'}, {'linux': '1'}))
        self.assertTrue(gui.reboot_needed({'linux': '1'}, {'linux': '2'}))
        self.assertFalse(gui.reboot_needed(None, {'linux': '2'}))
        self.assertTrue(gui.reboot_needed(None, None, True))

    def test_all_actions_are_explicit_without_shell_interpolation(self):
        with self.assertRaises(ValueError): gui.action_command('discord')
        self.assertEqual(gui.action_command('callas'), ['/usr/local/libexec/callas-release'])
        with self.assertRaises(ValueError): gui.action_command('sistema; reboot')

    def test_deployment_replaces_same_id_and_documents_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / 'prefix with spaces'; home = Path(tmp) / 'home'
            old_umask = os.umask(0o077)
            self.addCleanup(os.umask, old_umask)
            entry, target = installer.deploy(ROOT / 'atualizador/callas-update-gui.py', prefix)
            installer.configure_user(home, entry, target)
            installer.configure_user(home, entry, target)
            self.assertEqual(len(list((home / '.local/share/applications').glob('*.desktop'))), 1)
            self.assertIn(b'Terminal=false', entry)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o755)
            self.assertEqual((home / 'Documentos/Callas OS/Atualizador do sistema.desktop').read_bytes(), entry)
            self.assertIn(str(target), (home / 'Documentos/Callas OS/atualizador-do-sistema.sh').read_text())
            self.assertEqual((target.parent / 'callas-update-askpass').stat().st_mode & 0o777, 0o755)

    def test_monitor_choices_show_all_outputs_and_current_primary(self):
        with patch.object(gui.MonitorDialog, 'detect'):
            dialog = gui.MonitorDialog()
        dialog.detected(0, '[{"name":"DP-1","priority":1,"size":{"width":1920,"height":1080}},'
                           '{"name":"HDMI-A-1","priority":2},{"name":"DP-3","priority":3}]', '')
        self.assertEqual(dialog.choices.count(), 3)
        self.assertIn('Principal atual', dialog.choices.itemAt(0).widget().text())
        self.assertFalse(dialog.choices.itemAt(0).widget().isEnabled())
        self.assertTrue(dialog.choices.itemAt(2).widget().isEnabled())
        with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.No), patch.object(dialog, 'execute') as execute:
            dialog.select('DP-3')
            execute.assert_not_called()
        with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.Yes), patch.object(dialog, 'execute') as execute:
            dialog.choices.itemAt(2).widget().click()
            args = execute.call_args.args[0]
            self.assertEqual(args[:2], ['--set-primary', 'DP-3'])
            self.assertIn('--gui-auth', args)
            self.assertIn('HDMI-A-1', args[3])
        dialog.close()

    def test_monitor_empty_and_error_are_visible(self):
        with patch.object(gui.MonitorDialog, 'detect'):
            dialog = gui.MonitorDialog()
        dialog.detected(0, '[]', '')
        self.assertIn('Nenhum monitor', dialog.message.text())
        dialog.detected(1, '', 'Sessão indisponível')
        self.assertEqual(dialog.message.text(), 'Sessão indisponível')
        dialog.close()

    def test_symlink_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target'; target.write_text('preserve')
            link = Path(tmp) / 'link'; link.symlink_to(target)
            with self.assertRaises(ValueError): installer.atomic(link, b'replace')
            self.assertEqual(target.read_text(), 'preserve')

    def test_real_pty_stream_and_interactive_reply_without_privileges(self):
        window = gui.Window()
        popen = subprocess.Popen
        def safe_process(argv, **kwargs):
            return popen(['/usr/bin/python3', '-u', '-c',
                'import sys; print("installing demo 35%", flush=True); print("Resposta:", flush=True); answer=input(); print("recebido:"+answer, flush=True)'], **kwargs)
        with patch.object(gui, 'action_command', return_value=['/usr/bin/true']), \
             patch.object(gui, 'package_state', return_value={}), \
             patch.object(gui.subprocess, 'Popen', side_effect=safe_process):
            window.start('nativos')
        deadline = time.monotonic() + 5
        sent = False
        while window.process is not None and time.monotonic() < deadline:
            APP.processEvents()
            if 'Resposta:' in window.details.toPlainText() and not sent:
                window.response.setText('sim'); window.send_response(); sent = True
            time.sleep(0.01)
        self.assertIsNone(window.process)
        self.assertIn('recebido:sim', window.details.toPlainText())
        self.assertEqual(window.stage.text(), 'Concluído com sucesso')
        window.close(); window.deleteLater()

    def test_system_and_callas_offer_reboot_only_after_success_without_package_changes(self):
        class Process:
            def __init__(self, code): self.returncode = code
            def poll(self): return self.returncode
        for action in ('sistema', 'callas'):
            for code in (0, 1, 2):
                with self.subTest(action=action, code=code):
                    window = gui.Window()
                    self.assertTrue(window.restart_panel.isHidden())
                    master, slave = gui.pty.openpty(); os.close(slave)
                    window.master = master; os.set_blocking(master, False)
                    window.notifier = gui.QSocketNotifier(master, gui.QSocketNotifier.Read, window)
                    window.process = Process(code); window.action = action; window.before = {}
                    with patch.object(gui, 'package_state', return_value={}), \
                         patch.object(gui.Path, 'exists', return_value=False), \
                         patch.object(gui.subprocess, 'run') as reboot:
                        window.poll()
                        self.assertEqual(window.restart_panel.isHidden(), code != 0)
                        self.assertEqual(window.reboot_pending, code == 0)
                        reboot.assert_not_called()
                        if code == 0:
                            from PySide6.QtWidgets import QPushButton
                            buttons = window.restart_panel.findChildren(QPushButton)
                            self.assertEqual([button.text() for button in buttons], ['Reiniciar agora', 'Mais tarde'])
                            buttons[1].click()
                            self.assertTrue(window.restart_panel.isHidden())
                            reboot.assert_not_called()
                    window.close(); window.deleteLater()
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_window_and_process_error_success_deferral(self):
        from PySide6.QtWidgets import QApplication
        self.app = APP
        window = gui.Window()
        class Process:
            def __init__(self, code): self.returncode = code
            def poll(self): return self.returncode
        for code, title in [(0, 'Concluído com sucesso'), (1, 'A operação não foi concluída'),
                            (2, 'Algumas atualizações ficaram pendentes')]:
            master, slave = gui.pty.openpty(); os.close(slave)
            window.master = master; os.set_blocking(master, False)
            window.notifier = gui.QSocketNotifier(master, gui.QSocketNotifier.Read, window)
            window.process = Process(code); window.action = 'nativos'; window.before = {'linux': '1'}
            with patch.object(gui, 'package_state', return_value={'linux': '2'}): window.poll()
            self.assertEqual(window.stage.text(), title)
            self.assertEqual(window.reboot_pending, code == 0)
            window.reboot_pending = False
        window.close()
        window.deleteLater()
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

if __name__ == '__main__': unittest.main()
