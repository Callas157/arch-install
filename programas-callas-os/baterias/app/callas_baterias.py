"""Bandeja única: teclado FreeWolf F75 e mouse Attack Shark.

Reutiliza o app Attack Shark PT-BR fornecido pelo usuário (MIT).
"""
import configparser
import os
import select
import sys
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMessageBox
from sharktray.app import Tray


def parse_keyboard(data):
    if (len(data) >= 6 and data[:5] == bytes.fromhex('aa55cc330e')
            and data[5] <= 100):
        return data[5]
    return None


def read_keyboard():
    for device in Path('/sys/bus/hid/devices').glob('0003:1A2C:8FFF.*'):
        if not (device / 'report_descriptor').read_bytes().startswith(bytes.fromhex('0602ff')):
            continue
        for node in device.glob('hidraw/hidraw*'):
            fd = os.open('/dev/' + node.name, os.O_RDWR | os.O_NONBLOCK)
            try:
                packet = bytes.fromhex('00aa55cc330e') + bytes(59)
                if os.write(fd, packet) != len(packet):
                    raise RuntimeError('consulta incompleta')
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    remaining = max(0, deadline - time.monotonic())
                    if not select.select([fd], [], [], remaining)[0]:
                        break
                    try:
                        data = os.read(fd, 64)
                    except BlockingIOError:
                        continue
                    if not data:
                        break
                    value = parse_keyboard(data)
                    if value is not None:
                        return value
            finally:
                os.close(fd)
    raise RuntimeError('sem resposta; pode estar dormindo ou desconectado')


class KeyboardMonitor(QThread):
    result = Signal(object, str)

    def run(self):
        while not self.isInterruptionRequested():
            try:
                self.result.emit(read_keyboard(), '')
            except PermissionError:
                self.result.emit(None, 'sem permissão; reconecte o dongle')
            except Exception as error:
                self.result.emit(None, str(error))
            for _ in range(600):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)


class UnifiedTray(Tray):
    def __init__(self):
        self.keyboard_value = None
        self.keyboard_error = 'consultando…'
        super().__init__()
        self.keyboard_monitor = KeyboardMonitor(self)
        self.keyboard_monitor.result.connect(self.keyboard_update)
        self.keyboard_monitor.start()
        QApplication.instance().aboutToQuit.connect(self.stop_keyboard)

    def _build_menu(self):
        # Mantém os objetos internos usados pelas preferências originais,
        # mas mostra apenas as quatro entradas solicitadas pelo usuário.
        super()._build_menu()
        for action in self.menu.actions():
            action.setVisible(False)
        self.keyboard_action = QAction('FreeWolf F75: consultando…', self.menu)
        self.menu.insertAction(self.header, self.keyboard_action)
        self.keyboard_action.setEnabled(False)
        self.header.setEnabled(True)
        self.header.setVisible(True)
        self.header.triggered.connect(self.open_preferences)
        self.menu.addSeparator()
        self.menu.addAction('Sobre', self.about)
        self.menu.addAction('Sair', QApplication.quit)

    def _update_visual(self):
        super()._update_visual()
        r = self.reading
        level = f'{r.level}%' if r.present and r.level_known else '—'
        connection = ' (cabo)' if r.cable else ''
        self.header.setText(f'Attack Shark: {level}{connection}')
        self.subheader.setVisible(False)
        self.eta_line.setVisible(False)
        value = self.keyboard_value
        if value is None:
            keyboard_text = 'FreeWolf F75: —'
        else:
            keyboard_text = f'FreeWolf F75: {value}%'
        self.keyboard_action.setText(keyboard_text)
        keyboard_tip = keyboard_text if value is not None else f'{keyboard_text} ({self.keyboard_error})'
        self.setToolTip(self.toolTip() + '\n' + keyboard_tip)

    def keyboard_update(self, value, error):
        self.keyboard_value = value
        self.keyboard_error = error
        self._update_visual()

    def stop_keyboard(self):
        self.keyboard_monitor.requestInterruption()
        self.keyboard_monitor.wait()

    def about(self):
        QMessageBox.about(None, 'Sobre o Callas Baterias',
            'Callas Baterias 1.0\n\n'
            'Teclado FreeWolf F75 e mouse Attack Shark em uma bandeja.\n'
            'Clique na linha do Attack Shark para abrir suas preferências.\n\n'
            'Mouse: código original de gabrielmf1998, licença MIT, '
            'com as adaptações PT-BR fornecidas pelo usuário.\n'
            'Teclado: consulta de bateria compatível com OpenRGBAK820Plugin.\n'
            'O estado de carga do teclado ainda não foi validado.\n\n'
            'O Solar permanece separado para o fone G733.')

    def autostart_enabled(self):
        path = Path.home() / '.config/autostart/callas-baterias.desktop'
        if not path.exists():
            return Path('/etc/xdg/autostart/callas-baterias.desktop').is_file()
        config = configparser.ConfigParser(interpolation=None)
        try:
            config.read(path)
            return not config.getboolean('Desktop Entry', 'Hidden', fallback=False)
        except (OSError, configparser.Error, ValueError):
            return False

    def set_autostart(self, on):
        path = Path.home() / '.config/autostart/callas-baterias.desktop'
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if on:
                path.write_text('[Desktop Entry]\nType=Application\nName=Callas Baterias\n'
                    'Exec=/bin/bash -c "exec ~/.local/bin/callas-baterias"\n'
                    'Icon=battery\nTerminal=false\nCategories=Utility;\n')
            else:
                path.write_text('[Desktop Entry]\nType=Application\nName=Callas Baterias\nHidden=true\n')
        except OSError:
            pass
        return self.autostart_enabled()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Callas Baterias')
    app.setDesktopFileName('callas-baterias')
    app.setQuitOnLastWindowClosed(False)
    runtime = QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation)
    lock = QLockFile(str(Path(runtime) / 'callas-baterias.lock'))
    if not lock.tryLock(100):
        return 0
    tray = UnifiedTray()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
