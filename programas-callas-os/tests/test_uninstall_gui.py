"""Exercise real Qt inventory process and selection without removing host apps."""
import gc
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
UP = Path(__file__).resolve().parents[1] / 'atualizador'
spec = importlib.util.spec_from_file_location('uninstall_gui_test', UP / 'callas-update-gui.py')
gui = importlib.util.module_from_spec(spec); spec.loader.exec_module(gui)
APP = gui.QApplication.instance() or gui.QApplication([])

APPS = [dict(kind='flatpak-user', id='app/com.example.App/x86_64/stable', name='Example', version='1.0',
             source='Flatpak — usuário', blocked=False, reason='Preserva dados'),
        dict(kind='native', id='plasma-desktop', name='Plasma', version='1.0', source='Nativo / AUR',
             blocked=True, reason='Componente essencial')]


def wait(dialog):
    deadline = time.monotonic() + 5
    while dialog.process is not None and time.monotonic() < deadline:
        APP.processEvents(); time.sleep(.01)
    assert dialog.process is None, 'GUI process did not finish'


class UninstallGuiTests(unittest.TestCase):
    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        for widget in APP.topLevelWidgets(): widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()

    def fixture(self, folder):
        helper = Path(folder) / 'helper'
        state = Path(folder) / 'state'
        state.write_text(json.dumps(APPS))
        helper.write_text('#!/usr/bin/python3\nimport json, pathlib, sys, os\n'
            f'p = pathlib.Path({str(state)!r})\n'
            'if sys.argv[1:] == ["--list"]: print(p.read_text())\n'
            'else:\n'
            ' assert sys.argv[1:] == ["--remove", "flatpak-user", "app/com.example.App/x86_64/stable"]\n'
            ' assert "CALLAS_KERNEL_UPDATE_CONTEXT" not in os.environ\n'
            ' assert os.environ.get("SUDO_ASKPASS")\n'
            ' p.write_text("[]")\n print("Remoção simulada; dados preservados")\n')
        helper.chmod(0o755)
        return helper

    def test_window_size_filter_block_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(gui.QTimer, 'singleShot'):
            helper = self.fixture(folder)
            with patch.object(gui, 'UNINSTALL_HELPER', str(helper)):
                parent = gui.Window(); dialog = gui.UninstallDialog(parent)
                self.assertEqual(dialog.size(), parent.size())
                dialog.refresh(); wait(dialog)
                self.assertEqual(dialog.table.rowCount(), 1)
                dialog.table.selectRow(0)
                self.assertTrue(dialog.remove.isEnabled())
                with patch.object(gui.QMessageBox, 'exec', return_value=gui.QMessageBox.No), \
                     patch.object(dialog, 'run_helper') as run:
                    dialog.uninstall(); run.assert_not_called()
                dialog.protected.setChecked(True)
                self.assertEqual(dialog.table.rowCount(), 2)
                dialog.table.selectRow(1)
                self.assertFalse(dialog.remove.isEnabled())
                self.assertIn('Componente essencial', dialog.info.text())
                dialog.search.setText('example')
                self.assertEqual(dialog.table.rowCount(), 1)
                dialog.close(); parent.close()

    def test_user_removal_refreshes_and_uses_no_sudo(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(gui.QTimer, 'singleShot'):
            helper = self.fixture(folder)
            with patch.object(gui, 'UNINSTALL_HELPER', str(helper)), \
                    patch.dict(os.environ, {'CALLAS_KERNEL_UPDATE_CONTEXT': 'general'}):
                dialog = gui.UninstallDialog()
                dialog.refresh(); wait(dialog); dialog.table.selectRow(0)
                with patch.object(gui.QMessageBox, 'exec', return_value=gui.QMessageBox.Yes), \
                     patch.object(gui.subprocess, 'run'):
                    dialog.uninstall(); wait(dialog)
                self.assertEqual(dialog.table.rowCount(), 0)
                self.assertIn('Example desinstalado', dialog.status.text())
                self.assertIn('Remoção simulada', dialog.details.toPlainText())
                dialog.close()

    def test_busy_prevents_closing_and_missing_helper_is_clear(self):
        with patch.object(gui.QTimer, 'singleShot'):
            dialog = gui.UninstallDialog()
            dialog.set_busy(True)
            with patch.object(gui.QDialog, 'reject') as reject:
                dialog.reject(); reject.assert_not_called()
            self.assertFalse(dialog.back.isEnabled())
            self.assertFalse(dialog.remove.isEnabled())
            dialog.set_busy(False)
            with patch.object(gui, 'UNINSTALL_HELPER', '/nonexistent/callas-uninstall'):
                dialog.refresh()
            self.assertIn('Callas OS Update', dialog.status.text())
            self.assertFalse(dialog.busy)
            dialog.close()

if __name__ == '__main__': unittest.main()
