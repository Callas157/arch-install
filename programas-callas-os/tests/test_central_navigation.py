"""Single-window navigation and icon display without changing host packages."""
import gc
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
UP = Path(__file__).resolve().parents[1] / 'atualizador'
spec = importlib.util.spec_from_file_location('central_navigation', UP / 'callas-update-gui.py')
gui = importlib.util.module_from_spec(spec); spec.loader.exec_module(gui)
from PySide6.QtCore import QCoreApplication, QEvent
APP = gui.QApplication.instance() or gui.QApplication([])

class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.dialog_exec = patch.object(gui.QDialog, 'exec')
        self.dialog_exec.start(); self.addCleanup(self.dialog_exec.stop)

    def tearDown(self):
        for widget in APP.topLevelWidgets(): widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); gc.collect()

    def test_submenus_share_one_window_and_back_returns_home(self):
        window = gui.Window(); window.show()
        with patch.object(gui.QDialog, 'exec'), patch.object(gui.QTimer, 'singleShot'), patch.object(gui.MonitorDialog, 'detect'):
            for open_page in (window.maintenance, window.native_apps, window.uninstall_apps, window.monitors):
                open_page(); APP.processEvents()
                page = window.pages.currentWidget()
                self.assertIsNot(page, window.home_page)
                self.assertFalse(page.isWindow())
                self.assertIs(page.window(), window)
                self.assertEqual([w for w in APP.topLevelWidgets() if w.isVisible()], [window])
                page.reject(); self.assertIs(window.pages.currentWidget(), window.home_page)

    def test_confirmation_is_inline_cancel_is_safe_and_accept_runs_once(self):
        window = gui.Window(); window.show(); calls = []
        with patch.object(gui.QMessageBox, 'exec') as modal:
            window.confirm_action('Confirme', 'Instalar?', lambda: calls.append('yes'), 'Instalar')
            self.assertIs(window.pages.currentWidget(), window.confirm_page)
            window.confirm_cancel.click(); self.assertEqual(calls, [])
            self.assertIs(window.pages.currentWidget(), window.home_page)
            window.confirm_action('Confirme', 'Instalar?', lambda: calls.append('yes'), 'Instalar')
            window.confirm_yes.click(); window.confirm_yes.click()
            self.assertEqual(calls, ['yes']); modal.assert_not_called()

    def test_busy_subpage_prevents_navigation_and_main_window_closing(self):
        window = gui.Window(); window.show()
        with patch.object(gui.QTimer, 'singleShot'):
            window.uninstall_apps(); page = window.pages.currentWidget(); page.set_busy(True)
            window.native_apps(); self.assertIs(window.pages.currentWidget(), page)
            self.assertFalse(window.close())
            self.assertTrue(window.isVisible())
            page.set_busy(False); page.reject()
            self.assertIs(window.pages.currentWidget(), window.home_page)

    def test_embedded_uninstall_confirmation_never_removes_on_cancel(self):
        window = gui.Window(); window.show()
        with patch.object(gui.QTimer, 'singleShot'):
            window.uninstall_apps()
        page = window.active_page
        page.apps = [dict(kind='native',id='spotify',name='Spotify',icon='spotify',version='1',
                          source='Nativo / AUR',blocked=False,reason='Aplicativo')]
        page.filter_apps(); page.table.selectRow(0)
        with patch.object(page, 'run_helper') as run:
            page.uninstall(); self.assertIs(window.pages.currentWidget(), window.confirm_page)
            window.confirm_cancel.click(); run.assert_not_called()
            self.assertIs(window.pages.currentWidget(), page)
            page.uninstall(); window.confirm_yes.click()
            self.assertEqual(run.call_args.args[:2], (['--remove', 'native', 'spotify'], True))
            self.assertEqual(run.call_count, 1)

    def test_maintenance_and_native_update_return_to_main_progress(self):
        window = gui.Window()
        with patch.object(window, 'start') as start:
            window.maintenance(); window.active_page.choose('clean')
            self.assertIs(window.pages.currentWidget(), window.home_page)
            start.assert_called_once_with('clean')
            start.reset_mock(); window.native_apps(); window.active_page.update_button.click()
            self.assertIs(window.pages.currentWidget(), window.home_page)
            start.assert_called_once_with('nativos')

    def test_uninstall_name_cell_has_icon_and_keeps_package_identity(self):
        with patch.object(gui.QTimer, 'singleShot'):
            page = gui.UninstallDialog()
        page.apps = [dict(kind='native',id='spotify',name='Spotify',icon='spotify',version='1',
                          source='Nativo / AUR',blocked=False,reason='Aplicativo')]
        page.filter_apps(); page.table.selectRow(0)
        self.assertFalse(page.table.item(0,0).icon().isNull())
        self.assertEqual(page.selected()['id'], 'spotify')
        self.assertGreaterEqual(page.table.iconSize().width(), 28)

if __name__ == '__main__': unittest.main()
