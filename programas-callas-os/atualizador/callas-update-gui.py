#!/usr/bin/python3
"""KDE updater frontend. All privileged operations stay in existing helpers."""
import codecs
import errno
import fcntl
import os
from pathlib import Path
import pty
import pwd
import re
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, QSocketNotifier, QSize
from PySide6.QtGui import QIcon, QPalette, QColor, QFont, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QProgressBar, QPlainTextEdit, QFrame,
    QLineEdit, QMessageBox, QInputDialog, QStyle, QDialog)

BACKEND = '/usr/local/libexec/put-update'
ID = 'io.github.Callas157.AtualizadorDoSistema'
CRITICAL = ('linux', 'linux-lts', 'linux-zen', 'linux-hardened', 'systemd', 'glibc',
            'nvidia-utils', 'nvidia-open-dkms', 'mesa', 'linux-firmware')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)')

def package_state():
    result = subprocess.run(['/usr/bin/pacman', '-Q', *CRITICAL], capture_output=True,
                            text=True, timeout=15)
    if result.returncode not in (0, 1):
        raise RuntimeError('Não consegui consultar os componentes do sistema.')
    return {line.split()[0]: line.split()[1] for line in result.stdout.splitlines() if len(line.split()) == 2}

def reboot_needed(before, after, marker=False):
    return marker or (before is not None and after is not None and before != after)

def progress_state(text):
    """Only use real percentages; activities without totals remain animated."""
    lower = text.casefold()
    stage = None
    if any(s in lower for s in ('baixando', 'downloading', 'retrieving packages', 'download')):
        stage = 'Baixando atualizações'
    if any(s in lower for s in ('instalando', 'installing', 'upgrading', 'atualizando', 'reinstalling')):
        stage = 'Instalando atualizações'
    if any(s in lower for s in ('verificando', 'checking', 'validando', 'integrity')):
        stage = 'Verificando arquivos e sistema'
    if '==>' in text:
        stage = text.split('==>', 1)[1].strip()
    percentages = re.findall(r'(?<!\d)(100|[1-9]?\d)%', text)
    return stage, int(percentages[-1]) if percentages else None

def action_command(action):
    user = pwd.getpwuid(os.getuid()).pw_name
    if action in ('nativos', 'discord', 'sistema', 'flatpaks'):
        return [BACKEND, '--manual', action]
    if action in ('clean', 'report', 'orphans'):
        return ['/usr/local/libexec/callas-maintenance', '--' + action, user]
    if action == 'repair': return [BACKEND, '--instalar']
    if action == 'games': return ['/usr/local/libexec/callas-game-logs', '--collect', user]
    if action == 'callas': return ['/usr/local/libexec/callas-release']
    raise ValueError('Função desconhecida')

def option_icon(name):
    paths = {
        'edit-clear': '<path d="m9 4 11 11-7 7L2 11zM6 15l7-7M13 22h9"/>',
        'applications-all': '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
        'discord': '<path d="M7 5 3 7 1 17l5 3 2-3h8l2 3 5-3-2-10-4-2-1 2H8z"/><circle cx="8" cy="12" r="1"/><circle cx="16" cy="12" r="1"/>',
        'system-software-update': '<path d="M20 8a8 8 0 0 0-14-2L3 9m0-5v5h5M4 16a8 8 0 0 0 14 2l3-3m0 5v-5h-5"/>',
        'system-upgrade': '<path d="M12 21V3m-7 7 7-7 7 7M4 17v4h16v-4"/>',
        'application-exit': '<path d="M10 3H3v18h7M9 12h13m-5-5 5 5-5 5"/>',
        'view-list-details': '<path d="M8 5h13M8 12h13M8 19h13M3 5h1M3 12h1M3 19h1"/>',
        'folder-open': '<path d="M2 19V5h7l2 3h11l-3 11zM2 19l4-8h16"/>',
        'system-reboot': '<path d="M12 2v9M6 5a9 9 0 1 0 12 0"/>',
        'appointment-soon': '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',
        'go-next': '<path d="M3 12h18m-7-7 7 7-7 7"/>',
    }
    if name not in paths: return QIcon.fromTheme(name)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24"><g fill="none" stroke="#88caff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + paths[name] + '</g></svg>'
    pixmap = QPixmap(); pixmap.loadFromData(svg.encode(), 'SVG')
    return QIcon(pixmap)

class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.process = None
        self.master = None
        self.notifier = None
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.before = None
        self.action = None
        self.pending = ''
        self.reboot_pending = False
        self.setWindowTitle('Atualizador do sistema')
        self.setWindowIcon(option_icon('system-software-update'))
        self.resize(900, 770)
        self.setMinimumSize(690, 620)
        self.setStyleSheet('''
            QWidget { font-size: 14px; }
            QLabel#title { font-size: 27px; font-weight: 700; }
            QLabel#subtitle { color: #aebac7; }
            QLabel#stage { font-size: 17px; font-weight: 600; }
            QPushButton { padding: 11px 18px; border: 1px solid #46515f;
                border-radius: 9px; background: #303945; }
            QPushButton:hover { background: #3e4c5d; border-color: #71b8f5; }
            QPushButton:pressed { background: #233548; }
            QPushButton:disabled { color: #7c8794; background: #282e36; }
            QPushButton#primary { background: #286ba5; border-color: #559bce; }
            QProgressBar { border: none; background: #343e4b; border-radius: 5px;
                height: 13px; text-align: center; }
            QProgressBar::chunk { background: #62b5f4; border-radius: 5px; }
            QPlainTextEdit, QLineEdit { background: #181e25; border: 1px solid #414d5a;
                border-radius: 7px; padding: 7px; }
            QFrame#card { background: #252d37; border-radius: 12px; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 25, 32, 24)
        layout.setSpacing(16)
        emblem = QLabel()
        icon = option_icon('system-software-update')
        emblem.setPixmap(icon.pixmap(56, 56))
        emblem.setAlignment(Qt.AlignCenter)
        layout.addWidget(emblem)
        title = QLabel('Atualizador do sistema', objectName='title')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel('Cuide do seu Callas OS em um só lugar', objectName='subtitle')
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        self.home = QWidget()
        grid = QGridLayout(self.home)
        grid.setSpacing(12)
        self.buttons = []
        entries = (
            ('Limpeza e manutenção', 'edit-clear', self.maintenance),
            ('Aplicativos nativos', 'applications-all', lambda: self.start('nativos')),
            ('Atualizar Discord', 'discord', lambda: self.start('discord')),
            ('Atualizar geral', 'system-software-update', lambda: self.start('sistema')),
            ('Callas OS Update', 'system-upgrade', lambda: self.start('callas')),
            ('Sair', 'application-exit', self.close),
        )
        for i, (label, name, callback) in enumerate(entries):
            button = self.button(label, name, callback)
            button.setMinimumSize(265, 68)
            grid.addWidget(button, i // 2, i % 2)
            self.buttons.append(button)
        row = QHBoxLayout()
        row.addStretch(); row.addWidget(self.home); row.addStretch()
        layout.addLayout(row)
        card = QFrame(objectName='card')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        self.stage = QLabel('Pronto para atualizar', objectName='stage')
        self.stage.setWordWrap(True)
        self.status = QLabel('Escolha uma função acima. A autorização será solicitada quando necessário.')
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100); self.bar.setValue(0); self.bar.setTextVisible(False)
        card_layout.addWidget(self.stage); card_layout.addWidget(self.status); card_layout.addWidget(self.bar)
        layout.addWidget(card)
        self.details_button = self.button('Mostrar detalhes', 'view-list-details', self.toggle_details)
        layout.addWidget(self.details_button, alignment=Qt.AlignHCenter)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(5000)
        self.details.setFont(QFont('monospace', 10))
        self.details.setMinimumHeight(160)
        self.details.hide()
        layout.addWidget(self.details, 1)
        self.input_row = QWidget()
        il = QHBoxLayout(self.input_row); il.setContentsMargins(0, 0, 0, 0)
        self.response = QLineEdit()
        self.response.setPlaceholderText('Quando os detalhes pedirem uma resposta, digite aqui e envie')
        self.response.returnPressed.connect(self.send_response)
        il.addWidget(self.response)
        il.addWidget(self.button('Enviar resposta', 'go-next', self.send_response))
        self.input_row.hide(); layout.addWidget(self.input_row)
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addWidget(self.button('Abrir logs', 'folder-open', self.open_logs))
        footer.addStretch()
        self.restart_panel = QWidget()
        rl = QVBoxLayout(self.restart_panel); rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel('Atualização concluída. Reinicie para aplicar as mudanças.'))
        rr = QHBoxLayout(); rr.addStretch()
        rr.addWidget(self.button('Mais tarde', 'appointment-soon', self.defer_reboot))
        reboot = self.button('Reiniciar agora', 'system-reboot', self.restart)
        reboot.setObjectName('primary'); rr.addWidget(reboot)
        rl.addLayout(rr)
        self.restart_panel.hide(); footer.addWidget(self.restart_panel)
        layout.addLayout(footer)
        self.timer = QTimer(self); self.timer.setInterval(150); self.timer.timeout.connect(self.poll)

    def button(self, text, icon, slot):
        button = QPushButton(option_icon(icon), text)
        button.setIconSize(QSize(25, 25)); button.clicked.connect(slot)
        return button

    def toggle_details(self):
        visible = not self.details.isVisible()
        self.details.setVisible(visible)
        self.input_row.setVisible(visible and self.process is not None)
        self.details_button.setText('Ocultar detalhes' if visible else 'Mostrar detalhes')

    def maintenance(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Limpeza e manutenção')
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Escolha a função de manutenção'))
        grid = QGridLayout(); layout.addLayout(grid)
        selected = []
        def choose(action):
            selected.append(action); dialog.accept()
        options = [('Limpeza segura', 'edit-clear', 'clean'),
            ('Espaço, backups e VMs', 'folder-open', 'report'),
            ('Verificar pacotes órfãos', 'applications-all', 'orphans'),
            ('Reparar agendamento', 'appointment-soon', 'repair'),
            ('Diagnóstico de jogo', 'view-list-details', 'games'),
            ('Atualizar Flatpaks', 'system-software-update', 'flatpaks')]
        for i, (title, icon, action) in enumerate(options):
            grid.addWidget(self.button(title, icon, lambda checked=False, a=action: choose(a)), i // 2, i % 2)
        layout.addWidget(self.button('Voltar', 'application-exit', dialog.reject), alignment=Qt.AlignHCenter)
        dialog.exec()
        if selected: self.start(selected[0])

    def start(self, action):
        if self.process is not None: return
        command = action_command(action)
        if not Path(command[0]).is_file():
            QMessageBox.warning(self, 'Função indisponível', 'O auxiliar desta função não está instalado: ' + command[0]); return
        if action == 'sistema' and QMessageBox.question(self, 'Atualizar geral',
            'Atualizar o sistema e os aplicativos? Esta função inclui kernel, com as proteções existentes do Callas OS.') != QMessageBox.Yes: return
        if action == 'repair' and QMessageBox.question(self, 'Reparar agendamento',
            'Reconfigurar o agendamento automático? As datas serão tratadas pelo reparo existente.') != QMessageBox.Yes: return
        self.action = action
        try: self.before = package_state()
        except (OSError, subprocess.SubprocessError, RuntimeError): self.before = None
        self.reboot_pending = False; self.restart_panel.hide()
        self.details.clear(); self.pending = ''; self.decoder.reset()
        self.stage.setText('Preparando atualização' if action not in ('report', 'games', 'orphans') else 'Preparando diagnóstico')
        self.status.setText('Aguardando autorização. Depois, acompanhe as etapas abaixo.')
        self.bar.setRange(0, 0)
        env = os.environ.copy()
        env['SUDO_ASKPASS'] = str(Path(__file__).resolve().with_name('callas-update-askpass'))
        env['PYTHONUNBUFFERED'] = '1'
        env['TERM'] = 'dumb'
        env.pop('CALLAS_KERNEL_UPDATE_CONTEXT', None)
        master, slave = pty.openpty()
        try:
            self.process = subprocess.Popen(['/usr/bin/sudo', '-A', '--', *command],
                stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True, close_fds=True)
        except OSError as exc:
            os.close(master); self.bar.setRange(0, 100); self.bar.setValue(0)
            self.stage.setText('Não foi possível iniciar'); self.status.setText(str(exc)); return
        finally: os.close(slave)
        self.master = master; os.set_blocking(master, False)
        self.notifier = QSocketNotifier(master, QSocketNotifier.Read, self)
        self.notifier.activated.connect(self.read_output)
        for button in self.buttons: button.setEnabled(False)
        self.input_row.setVisible(self.details.isVisible())
        if action in ('games', 'orphans'):
            self.details.show(); self.input_row.show(); self.details_button.setText('Ocultar detalhes')
        self.timer.start()

    def read_output(self, *_):
        if self.master is None: return
        while True:
            try: data = os.read(self.master, 16384)
            except BlockingIOError: break
            except OSError as exc:
                if exc.errno == errno.EIO: self.notifier.setEnabled(False); break
                raise
            if not data:
                self.notifier.setEnabled(False); break
            text = ANSI.sub('', self.decoder.decode(data)).replace('\r\n', '\n').replace('\r', '\n')
            self.details.moveCursor(self.details.textCursor().MoveOperation.End)
            self.details.insertPlainText(text)
            self.pending += text
            lines = self.pending.split('\n'); self.pending = lines.pop()[-8192:]
            for line in lines:
                stage, percent = progress_state(line)
                if stage:
                    self.stage.setText(stage)
                    self.bar.setRange(0, 0)
                if percent is not None:
                    self.bar.setRange(0, 100); self.bar.setValue(percent)
                    self.status.setText(f'{percent}% da etapa atual')
                elif line.strip(): self.status.setText(line.strip()[-180:])
            # Prompts often have no terminating newline.
            if self.pending.strip(): self.status.setText(self.pending.strip()[-180:])

    def send_response(self):
        if self.master is None: return
        value = self.response.text()
        try: os.write(self.master, (value + '\n').encode())
        except OSError: return
        self.response.clear()

    def poll(self):
        if self.process is None or self.process.poll() is None: return
        code = self.process.returncode
        self.read_output()
        self.timer.stop(); self.notifier.setEnabled(False); self.notifier.deleteLater(); self.notifier = None
        os.close(self.master); self.master = None; self.process = None
        for button in self.buttons: button.setEnabled(True)
        self.input_row.hide(); self.bar.setRange(0, 100)
        if code == 0:
            self.bar.setValue(100); self.stage.setText('Concluído com sucesso')
            self.status.setText('A função terminou. Você já pode escolher outra opção.')
            try: after = package_state()
            except (OSError, subprocess.SubprocessError, RuntimeError): after = None
            if self.action in ('sistema', 'nativos', 'callas', 'flatpaks'):
                self.reboot_pending = reboot_needed(self.before, after, Path('/run/reboot-required').exists())
                self.restart_panel.setVisible(self.reboot_pending)
                if after is None or self.before is None:
                    self.status.setText('Concluído. Não foi possível verificar automaticamente a necessidade de reinício.')
        elif code == 2 and self.action in ('nativos', 'flatpaks'):
            self.bar.setValue(0); self.stage.setText('Algumas atualizações ficaram pendentes')
            self.status.setText('Consulte os detalhes. Aplicativos podem aguardar a função Atualizar geral.')
            self.details.show(); self.details_button.setText('Ocultar detalhes')
        else:
            self.bar.setValue(0); self.stage.setText('A operação não foi concluída')
            self.status.setText(f'Código {code}. Confira os detalhes; a autorização também pode ter sido cancelada.')
            self.details.show(); self.details_button.setText('Ocultar detalhes')

    def defer_reboot(self):
        self.restart_panel.hide()
        self.status.setText('Reinício adiado. Você pode reiniciar depois pelo menu do KDE.')

    def restart(self):
        if not self.reboot_pending or self.process is not None: return
        if QMessageBox.question(self, 'Reiniciar agora', 'Salvou seus arquivos? Reiniciar o computador agora?') != QMessageBox.Yes: return
        result = subprocess.run(['/usr/bin/systemctl', 'reboot'], capture_output=True, text=True)
        if result.returncode: QMessageBox.warning(self, 'Não foi possível reiniciar', result.stderr)

    def open_logs(self):
        try:
            result = subprocess.run(['/usr/bin/xdg-user-dir', 'DOCUMENTS'], capture_output=True, text=True, timeout=5)
            documents = Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip().startswith('/') else Path.home() / 'Documentos'
            logs = documents / 'Callas OS' / 'Callas OS Logs'
            logs.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(['/usr/bin/xdg-open', str(logs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc: QMessageBox.warning(self, 'Logs', str(exc))

    def closeEvent(self, event):
        if self.process is not None:
            QMessageBox.information(self, 'Operação em andamento', 'Aguarde a operação terminar antes de fechar o atualizador.')
            event.ignore()
        else: event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Atualizador do sistema'); app.setDesktopFileName(ID)
    if sys.argv[1:] == ['--askpass']:
        value, ok = QInputDialog.getText(None, 'Autorizar atualização', 'Senha de administrador:', QLineEdit.Password)
        if ok: sys.stdout.write(value + '\n'); return 0
        return 1
    if os.geteuid() == 0:
        QMessageBox.warning(None, 'Atualizador', 'Abra o atualizador com seu usuário normal.'); return 1
    # A per-user lock prevents races; the socket activates the existing window.
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
    lock = open(runtime / 'callas-update-gui.lock', 'a')
    name = 'callas-update-gui-' + str(os.getuid())
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        socket = QLocalSocket(); socket.connectToServer(name)
        if socket.waitForConnected(1500): socket.write(b'activate'); socket.waitForBytesWritten(1000)
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer(); server.listen(name)
    palette = app.palette()
    for role, color in [(QPalette.Window, '#1d242d'), (QPalette.WindowText, '#edf2f7'),
        (QPalette.Base, '#181e25'), (QPalette.Text, '#edf2f7'), (QPalette.Button, '#303945'),
        (QPalette.ButtonText, '#edf2f7'), (QPalette.Highlight, '#378dcc'),
        (QPalette.HighlightedText, '#ffffff')]: palette.setColor(role, QColor(color))
    app.setPalette(palette)
    window = Window()
    def activate():
        connection = server.nextPendingConnection()
        if connection: connection.close(); connection.deleteLater()
        window.showNormal(); window.raise_(); window.activateWindow()
    server.newConnection.connect(activate)
    window.show()
    return app.exec()

if __name__ == '__main__': sys.exit(main())
