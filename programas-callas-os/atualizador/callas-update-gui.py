#!/usr/bin/python3
"""KDE updater frontend. All privileged operations stay in existing helpers."""
import codecs
import errno
import fcntl
import hashlib
import io
import tarfile
import tempfile
import urllib.request
import json
import os
from pathlib import Path
import pty
import pwd
import re
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, QSocketNotifier, QSize, QProcess, QProcessEnvironment
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

# The optional app is a separate download, never part of the OS install stage.
CODEX_REF = 'acd5e6ce5cff3f1ebaf12fcbe0954cc40ed31914'
CODEX_SHA256 = '32ab0b2f131670a45985b607bf4ad4bd79626eda57ccafde98e40e79757977c0'
CODEX_URL = ('https://raw.githubusercontent.com/Callas157/arch-install/' + CODEX_REF
             + '/programas-callas-os/codex/codex.tar.gz')
CODEX_ICON = '<svg\n  width="32"\n  height="32"\n  viewBox="0 0 20 20"\n  fill="none"\n  xmlns="http://www.w3.org/2000/svg"\n>\n  <path\n    d="M13.333 11.418C13.7002 11.418 13.9978 11.7159 13.998 12.083C13.998 12.4503 13.7003 12.748 13.333 12.748H10.833C10.4657 12.748 10.168 12.4503 10.168 12.083C10.1682 11.7159 10.4659 11.418 10.833 11.418H13.333Z"\n    fill="#88caff"\n  />\n  <path\n    d="M6.74121 7.34668C7.0561 7.15796 7.46442 7.26036 7.65332 7.5752L8.90332 9.6582C9.02949 9.86874 9.02961 10.1323 8.90332 10.3428L7.65332 12.4258C7.46441 12.7403 7.05597 12.8427 6.74121 12.6543C6.42637 12.4654 6.32396 12.0561 6.5127 11.7412L7.55664 10L6.5127 8.25879C6.324 7.94395 6.4265 7.53562 6.74121 7.34668Z"\n    fill="#88caff"\n  />\n  <path\n    fill-rule="evenodd"\n    clip-rule="evenodd"\n    d="M9.00195 1.75C10.1157 1.75021 11.1362 2.15467 11.9238 2.82227C12.1849 2.77516 12.455 2.74903 12.7295 2.74902C15.2262 2.74978 17.2507 4.77449 17.251 7.27148C17.2509 7.54581 17.2238 7.81473 17.1768 8.0752C17.8448 8.86317 18.2499 9.88479 18.25 10.999C18.2496 12.9609 16.9996 14.6284 15.2549 15.2549C14.6285 16.9998 12.9608 18.2497 10.999 18.25C9.88486 18.25 8.86411 17.8448 8.07617 17.1768C7.8155 17.2239 7.54592 17.2509 7.27148 17.251C4.77445 17.2507 2.7504 15.2257 2.75 12.7285C2.75003 12.4539 2.77608 12.1848 2.82324 11.9238C2.20237 11.1913 1.80895 10.2574 1.75684 9.23438L1.75 9.00098C1.75022 7.03932 2.99952 5.36992 4.74414 4.74316C5.37104 2.99851 7.04034 1.75002 9.00195 1.75ZM9.00195 3.07812C7.52474 3.07814 6.27967 4.08156 5.91504 5.44531C5.85362 5.67419 5.67418 5.85363 5.44531 5.91504C4.08208 6.27984 3.07836 7.52408 3.07812 9.00098C3.07826 9.88321 3.43594 10.682 4.01465 11.2607C4.1816 11.4283 4.24663 11.6728 4.18555 11.9014C4.11505 12.1653 4.07719 12.4429 4.07715 12.7285C4.07755 14.4925 5.50753 15.9225 7.27148 15.9229C7.55712 15.9228 7.83548 15.886 8.09961 15.8154L8.18652 15.7979C8.38833 15.7722 8.59297 15.8403 8.73926 15.9863C9.31801 16.5649 10.1168 16.9218 10.999 16.9219C12.4759 16.9216 13.7203 15.9183 14.085 14.5547L14.1133 14.4707C14.1918 14.2821 14.3542 14.1386 14.5547 14.085C15.9181 13.7203 16.9225 12.4758 16.9229 10.999C16.9228 10.1168 16.5648 9.31802 15.9863 8.73926C15.819 8.57175 15.7544 8.3274 15.8154 8.09863C15.886 7.83454 15.9238 7.5568 15.9238 7.27148C15.9235 5.50751 14.4924 4.07762 12.7285 4.07715C12.4424 4.0772 12.164 4.11412 11.9004 4.18457C11.672 4.24541 11.4282 4.18048 11.2607 4.01367C10.7183 3.47141 9.98306 3.12271 9.16699 3.08105L9.00195 3.07812Z"\n    fill="#88caff"\n  />\n</svg>\n'

def codex_launcher():
    return Path.home() / '.local/bin/callas-chat'

def install_codex():
    if os.geteuid() == 0: raise ValueError('Instale Codex no seu usuário normal, sem sudo.')
    print('==> Baixando Codex do GitHub…', flush=True)
    request = urllib.request.Request(CODEX_URL, headers={'User-Agent': 'CallasOS-Codex'})
    with urllib.request.urlopen(request, timeout=60) as response:
        if not response.url.startswith('https://'): raise ValueError('Download sem HTTPS recusado.')
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024: raise ValueError('Pacote excedeu o tamanho permitido.')
    if hashlib.sha256(data).hexdigest() != CODEX_SHA256:
        raise ValueError('O pacote Codex não corresponde à versão publicada. Tente novamente após atualizar a Central.')
    print('==> Integridade confirmada. Preparando instalação no seu perfil…', flush=True)
    with tempfile.TemporaryDirectory(prefix='callas-codex-') as folder:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            members = archive.getmembers()
            if (sum(m.size for m in members) > 16 * 1024 * 1024 or len(members) > 100
                    or any(not m.isfile() or Path(m.name).is_absolute() or '..' in Path(m.name).parts for m in members)):
                raise ValueError('Conteúdo inválido no pacote Codex.')
            archive.extractall(folder, members=members, filter='data')
        env = os.environ.copy()
        env.pop('CALLAS_KERNEL_UPDATE_CONTEXT', None)
        subprocess.run(['/usr/bin/python3', '-u', str(Path(folder)/'installer.py')],
                       check=True, env=env)
    print('==> Codex instalado! Abra pelo menu KDE ou pelo botão Codex da Central.', flush=True)


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
    if action in ('nativos', 'sistema', 'flatpaks'):
        return [BACKEND, '--manual', action]
    if action in ('clean', 'report', 'orphans'):
        return ['/usr/local/libexec/callas-maintenance', '--' + action, user]
    if action == 'repair': return [BACKEND, '--instalar']
    if action == 'games': return ['/usr/local/libexec/callas-game-logs', '--collect', user]
    if action == 'codex': return ['/usr/bin/python3', '-u', str(Path(__file__).resolve()), '--install-codex']
    if action == 'callas': return ['/usr/local/libexec/callas-release']
    raise ValueError('Função desconhecida')

def option_icon(name):
    if name == 'codex':
        pixmap = QPixmap(); pixmap.loadFromData(CODEX_ICON.encode(), 'SVG')
        return QIcon(pixmap)
    paths = {
        'edit-clear': '<path d="m9 4 11 11-7 7L2 11zM6 15l7-7M13 22h9"/>',
        'applications-all': '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
        'video-display': '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 22h8m-4-5v5"/>',
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

class MonitorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Monitores — definir monitor principal')
        self.setMinimumWidth(520)
        self.worker = None
        self.snapshot = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Definir monitor principal', objectName='stage'))
        self.message = QLabel('Detectando monitores…')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.choices = QVBoxLayout()
        layout.addLayout(self.choices)
        self.refresh = QPushButton('Atualizar lista')
        self.refresh.clicked.connect(self.detect)
        layout.addWidget(self.refresh)
        settings = QPushButton('Configurações de telas do KDE')
        settings.clicked.connect(lambda: subprocess.Popen(['systemsettings', 'kcm_kscreen']))
        layout.addWidget(settings)
        self.back = QPushButton('Voltar')
        self.back.clicked.connect(self.reject)
        layout.addWidget(self.back)
        self.detect()

    def execute(self, args, callback):
        self.refresh.setEnabled(False)
        self.back.setEnabled(False)
        for i in range(self.choices.count()): self.choices.itemAt(i).widget().setEnabled(False)
        process = QProcess(self)
        self.worker = process
        env = QProcessEnvironment.systemEnvironment()
        env.insert('SUDO_ASKPASS', str(Path(__file__).resolve().with_name('callas-update-askpass')))
        env.insert('CALLAS_MONITOR_GUI', '1')
        env.insert('PYTHONUNBUFFERED', '1')
        process.setProcessEnvironment(env)
        def finished(code, *_):
            if self.worker is not process: return
            output = bytes(process.readAllStandardOutput()).decode(errors='replace')
            error = bytes(process.readAllStandardError()).decode(errors='replace')
            self.worker = None
            self.refresh.setEnabled(True)
            self.back.setEnabled(True)
            callback(code, output, error)
            process.deleteLater()
        process.finished.connect(finished)
        process.errorOccurred.connect(lambda error: finished(1) if error == QProcess.FailedToStart else None)
        process.start('/usr/local/libexec/callas-monitores', args)

    def detect(self):
        if self.worker is not None: return
        while self.choices.count(): self.choices.takeAt(0).widget().deleteLater()
        self.message.setText('Detectando monitores…')
        self.execute(['--list-json'], self.detected)

    def detected(self, code, output, error):
        try:
            if code: raise RuntimeError(error or 'Não foi possível detectar os monitores.')
            self.snapshot = json.loads(output)
            if not self.snapshot: raise RuntimeError('Nenhum monitor ativo encontrado.')
            self.message.setText(f'{len(self.snapshot)} monitor(es) ativo(s). Escolha a tela principal.')
            for monitor in self.snapshot:
                size = monitor.get('size', {})
                primary = monitor.get('priority') == 1
                label = f"{monitor['name']} — {size.get('width', '?')} × {size.get('height', '?')}"
                label += ' — Principal atual' if primary else ' — Definir como principal'
                button = QPushButton(option_icon('video-display'), label)
                button.setEnabled(not primary)
                button.clicked.connect(lambda checked=False, name=monitor['name']: self.select(name))
                self.choices.addWidget(button)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            self.message.setText(str(exc))

    def select(self, name):
        if self.worker is not None: return
        if QMessageBox.question(self, 'Definir monitor principal',
            f'Definir {name} como principal para o painel, notificações e login?') != QMessageBox.Yes: return
        self.message.setText('Aplicando configuração. Autorize o ajuste do login quando solicitado…')
        self.execute(['--set-primary', name, '--expected', json.dumps([o['name'] for o in self.snapshot]),
                      '--gui-auth'], self.applied)

    def applied(self, code, output, error):
        if code:
            self.message.setText('Não foi possível concluir. As etapas já confirmadas podem ter sido aplicadas. '
                                 'O backup foi preservado quando criado. Atualize a lista para conferir.')
            QMessageBox.warning(self, 'Monitores', (error + '\n' + output).strip())
        else:
            self.detect()
            QMessageBox.information(self, 'Monitores', 'Monitor principal configurado. Confira o login na próxima entrada.')

    def reject(self):
        if self.worker is None: super().reject()

    def closeEvent(self, event):
        if self.worker is not None: event.ignore()
        else: event.accept()

class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.process = None
        self.monitor_dialog = None
        self.master = None
        self.notifier = None
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.before = None
        self.action = None
        self.pending = ''
        self.reboot_pending = False
        self.setWindowTitle('Central Callas OS')
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
        title = QLabel('Central Callas OS', objectName='title')
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
            ('Monitores', 'video-display', self.monitors),
            ('Atualizar geral', 'system-software-update', lambda: self.start('sistema')),
            ('Callas OS Update', 'system-upgrade', lambda: self.start('callas')),
            ('Codex', 'codex', self.codex),
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

    def monitors(self):
        if self.process is not None: return
        if self.monitor_dialog is not None:
            self.monitor_dialog.raise_(); self.monitor_dialog.activateWindow(); return
        self.monitor_dialog = MonitorDialog(self)
        try: self.monitor_dialog.exec()
        finally:
            self.monitor_dialog.deleteLater()
            self.monitor_dialog = None

    def codex(self):
        if self.process is not None: return
        launcher = codex_launcher()
        if launcher.is_file() and os.access(launcher, os.X_OK):
            try: subprocess.Popen([str(launcher)], start_new_session=True)
            except OSError as exc: QMessageBox.warning(self, 'Codex', str(exc))
            return
        if QMessageBox.question(self, 'Instalar Codex',
            'Baixar e instalar Codex no seu perfil e adicioná-lo ao menu KDE?\n\n'
            'O ditado baixa um modelo de voz de aproximadamente 1,5 GB. '
            'Depois, entre com sua própria conta ChatGPT. '
            'O sistema pedirá senha somente se faltar alguma dependência.') == QMessageBox.Yes:
            self.start('codex')

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
            argv = command if action == 'codex' else ['/usr/bin/sudo', '-A', '--', *command]
            self.process = subprocess.Popen(argv,
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
        if action == 'codex':
            self.stage.setText('Instalando Codex')
            self.status.setText('Baixando o aplicativo e preparando o menu KDE. Acompanhe os detalhes.')
            self.details.show(); self.input_row.hide(); self.details_button.setText('Ocultar detalhes')
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
            self.status.setText('Codex instalado. Abra pelo menu KDE ou pelo botão Codex.' if self.action == 'codex' else 'A função terminou. Você já pode escolher outra opção.')
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
    app.setApplicationName('Central Callas OS'); app.setDesktopFileName(ID)
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
        if socket.waitForConnected(1500):
            socket.write(b'monitors' if '--monitors' in sys.argv[1:] else b'activate'); socket.waitForBytesWritten(1000)
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
        if connection:
            connection.waitForReadyRead(1000)
            requested = bytes(connection.readAll())
            connection.close(); connection.deleteLater()
            if requested == b'monitors': QTimer.singleShot(0, window.monitors)
        window.showNormal(); window.raise_(); window.activateWindow()
    server.newConnection.connect(activate)
    window.show()
    if '--monitors' in sys.argv[1:]: QTimer.singleShot(0, window.monitors)
    return app.exec()

if __name__ == '__main__':
    if '--install-codex' in sys.argv[1:]:
        try: install_codex()
        except Exception as exc:
            print('Não foi possível instalar Codex: ' + str(exc), file=sys.stderr)
            sys.exit(1)
    else: sys.exit(main())
