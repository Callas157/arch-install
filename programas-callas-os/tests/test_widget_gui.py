"""Clock controls stay inside the Central and address each physical connector."""
import gc
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
UP = Path(__file__).resolve().parents[1] / 'atualizador'
spec = importlib.util.spec_from_file_location('widget_gui', UP / 'callas-update-gui.py')
gui = importlib.util.module_from_spec(spec); spec.loader.exec_module(gui)
from PySide6.QtCore import QCoreApplication, QEvent
APP = gui.QApplication.instance() or gui.QApplication([])
ROW = dict(id='plasmoid:com.github.prayag2.modernclock', name='com.github.prayag2.modernclock',
           source='plasmoid', title='Relógio Moderno', icon='clock', description='Hora e data',
           installed=True, version='1.0.0', size='82 KiB', download='Incluído no Callas OS', notice='')


class WidgetGuiTests(unittest.TestCase):
    def tearDown(self):
        for widget in APP.topLevelWidgets(): widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); gc.collect()

    def test_card_buttons_are_side_by_side_and_configuration_requires_install(self):
        dialog = gui.NativeAppsDialog(); dialog.apps = [dict(ROW)]; dialog.render_cards()
        dialog.show_defaults = lambda: None
        dialog.catalog_panel.show(); dialog.resize(940,820); dialog.show(); APP.processEvents()
        card = dialog.card_widgets[0][1]
        install = next(b for b in card.findChildren(gui.QPushButton) if b.text() == 'Instalado')
        configure = next(b for b in card.findChildren(gui.QPushButton) if b.text() == 'Configurar')
        self.assertEqual(install.geometry().y(), configure.geometry().y())
        self.assertTrue(configure.isEnabled())
        dialog.apps[0]['installed'] = False; dialog.render_cards()
        configure = next(b for b in dialog.card_widgets[0][1].findChildren(gui.QPushButton) if b.text() == 'Configurar')
        self.assertFalse(configure.isEnabled())

    def test_three_monitors_have_twelve_corner_buttons_and_back_stays_in_central(self):
        window = gui.Window(); window.show(); window.native_apps()
        dialog = window.active_page; dialog.apps = [dict(ROW)]; dialog.render_cards(); dialog.catalog_panel.show()
        screens = [dict(name=name, width=1920, height=1080) for name in ('DP-1','HDMI-1','DP-3')]
        with patch.object(dialog, 'run_helper') as run:
            dialog.show_clock_config()
            args, privileged, callback = run.call_args.args
            self.assertEqual(args, ['--screens']); self.assertFalse(privileged)
            callback(0, json.dumps(screens), '')
        page = dialog.clock_page; APP.processEvents()
        self.assertEqual(len(page.corner_buttons), 12)
        self.assertIs(page.window(), window); self.assertFalse(page.isWindow())
        with patch.object(dialog, 'run_helper') as run:
            page.corner_buttons[('DP-3','bottom-left')].click()
            self.assertEqual(run.call_args.args[:2], (['--move','DP-3','bottom-left'],False))
            run.call_args.args[2](0, '', '')
        self.assertIn('DP-3', page.status.text())
        with patch.object(dialog, 'run_helper') as run:
            page.edit.click(); self.assertEqual(run.call_args.args[:2], (['--edit'],False))
        page.back.click(); self.assertIs(dialog.stack.currentWidget(), dialog.content)
        self.assertIs(window.active_page, dialog)

    def test_install_widget_uses_no_administrative_authorization(self):
        dialog = gui.NativeAppsDialog(); dialog.apps = [dict(ROW,installed=False)]; dialog.render_cards()
        with patch.object(dialog, 'run_helper') as run:
            dialog.install_ids([ROW['id']], confirmed=True)
            self.assertFalse(run.call_args.args[1])

    def test_mixed_selection_keeps_widget_in_graphical_user_session(self):
        dialog = gui.NativeAppsDialog()
        native=dict(ROW,id='native:haruna',name='haruna',title='Haruna',source='repo',installed=False)
        dialog.apps = [native,dict(ROW,installed=False)]; dialog.render_cards()
        with patch.object(dialog, 'run_helper') as run, patch.object(dialog, 'refresh'), patch.object(gui.Path, 'is_file', return_value=False):
            dialog.install_ids(['native:haruna',ROW['id']], confirmed=True)
            self.assertEqual(run.call_args.args[0][2:], ['native:haruna'])
            self.assertTrue(run.call_args.args[1])
            run.call_args.args[2](0, 'Pacote instalado', '')
            self.assertEqual(run.call_args.args[0][2:], [ROW['id']])
            self.assertFalse(run.call_args.args[1])

    def test_failure_remains_visible_and_refresh_discards_disconnected_screens(self):
        dialog = gui.NativeAppsDialog(); dialog.apps = [dict(ROW)]
        with patch.object(dialog, 'run_helper') as run:
            dialog.show_clock_config(); run.call_args.args[2](0, '[{"name":"DP-1","width":1920,"height":1080}]', '')
            page=dialog.clock_page
            page.corner_buttons[('DP-1','top-left')].click()
            run.call_args.args[2](1, '', 'Monitor desconectado')
            self.assertIn('Monitor desconectado',page.status.text())
            page.refresh(); run.call_args.args[2](1, '', 'Sessão indisponível')
            self.assertEqual(page.corner_buttons,{})
            self.assertIn('Sessão indisponível',page.status.text())


if __name__ == '__main__': unittest.main()
