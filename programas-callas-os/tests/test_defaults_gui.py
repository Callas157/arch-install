"""Real Qt subprocess/card selection; no system packages are installed."""
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
spec = importlib.util.spec_from_file_location('defaults_gui', UP / 'callas-update-gui.py')
gui = importlib.util.module_from_spec(spec); spec.loader.exec_module(gui)
from PySide6.QtCore import QCoreApplication, QEvent
APP = gui.QApplication.instance() or gui.QApplication([])
ROWS = [dict(id='native:spotify', name='spotify', title='Spotify', icon='spotify', description='Música',
             source='aur', version='1.2', size='390 MiB', download='Não informado', installed=False, notice=''),
        dict(id='native:haruna', name='haruna', title='Haruna', icon='haruna', description='Vídeos',
             source='repo', version='1.0', size='10 MiB', download='3 MiB', installed=True, notice='')]


def wait(dialog):
    deadline = time.monotonic() + 5
    while dialog.process is not None and time.monotonic() < deadline:
        APP.processEvents(); time.sleep(.01)
    assert dialog.process is None


class DefaultsGuiTests(unittest.TestCase):
    def tearDown(self):
        for widget in APP.topLevelWidgets(): widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); gc.collect()

    def test_submenu_expands_in_same_window_and_selects_only_available(self):
        with tempfile.TemporaryDirectory() as temp:
            helper = Path(temp) / 'helper'; helper.write_text('#!/usr/bin/python3\nprint(' + repr(json.dumps(ROWS)) + ')\n'); helper.chmod(0o755)
            parent = gui.Window(); dialog = gui.NativeAppsDialog(parent); dialog.show(); APP.processEvents()
            self.assertFalse(dialog.catalog_panel.isVisible())
            with patch.object(gui, 'DEFAULTS_HELPER', str(helper)):
                dialog.defaults_button.click(); wait(dialog)
            self.assertTrue(dialog.catalog_panel.isVisible()); self.assertEqual(dialog.size(), parent.size())
            self.assertEqual(len(dialog.card_widgets), 2)
            dialog.select_available(True)
            self.assertEqual(dialog.selected_ids(), ['native:spotify'])
            self.assertFalse(dialog.checks['native:haruna'].isEnabled())
            self.assertTrue(dialog.install_selected.isEnabled())
            with patch.object(dialog, 'install_ids') as install:
                dialog.install_checked(); install.assert_called_once_with(['native:spotify'])
            dialog.select_available(False); self.assertEqual(dialog.selected_ids(), [])
            dialog.go_back(); self.assertFalse(dialog.catalog_panel.isVisible())
            dialog.show_defaults(); self.assertTrue(dialog.catalog_panel.isVisible())
            with patch.object(gui.QMessageBox, 'exec', return_value=gui.QMessageBox.No), patch.object(dialog, 'run_helper') as run:
                dialog.install_ids(['native:spotify']); run.assert_not_called()

    def test_existing_update_action_remains_separate(self):
        parent = gui.Window(); dialog = gui.NativeAppsDialog(parent)
        with patch.object(parent, 'start') as start:
            dialog.update_button.click(); start.assert_called_once_with('nativos')

    def test_restore_uses_only_confirmed_ids_and_refreshes_after_failure(self):
        dialog = gui.NativeAppsDialog(); dialog.apps = [dict(ROWS[0])]; dialog.render_cards()
        with patch.object(gui.QMessageBox, 'exec', return_value=gui.QMessageBox.Yes), \
                patch.object(dialog, 'run_helper') as run:
            dialog.install_ids(['native:spotify'])
            args, privileged, callback = run.call_args.args
            self.assertEqual(args[0], '--restore'); self.assertEqual(args[2:], ['native:spotify'])
            self.assertTrue(privileged)
            with patch.object(gui.subprocess, 'run'), patch.object(dialog, 'refresh') as refresh:
                callback(1, 'Instalação parcial', 'erro')
                self.assertIn('não concluída', refresh.call_args.kwargs['message'])
        dialog.set_busy(True)
        with patch.object(gui.QDialog, 'reject') as reject:
            dialog.reject(); reject.assert_not_called()
        self.assertFalse(dialog.update_button.isEnabled())
        dialog.set_busy(False)

    def test_icons_available_when_app_not_installed(self):
        with patch.object(gui, 'DEFAULT_ICONS', UP.parent.parent / 'assets/central-callas-os/default-app-icons.json'):
            for name in ('spotify', 'discord', 'steam', 'gpu-screen-recorder'):
                self.assertFalse(gui.default_app_icon(name).isNull())

if __name__ == '__main__': unittest.main()
