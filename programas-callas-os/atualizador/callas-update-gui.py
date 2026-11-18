#!/usr/bin/python3
"""KDE updater frontend. All privileged operations stay in existing helpers."""
import base64
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
    QGridLayout, QPushButton, QComboBox, QLabel, QProgressBar, QPlainTextEdit, QFrame,
    QLineEdit, QMessageBox, QInputDialog, QStyle, QDialog, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QScrollArea, QStackedWidget)

BACKEND = '/usr/local/libexec/put-update'
NVIDIA_HELPER = '/usr/local/libexec/callas-kernel-policy'
UNINSTALL_HELPER = '/usr/local/libexec/callas-uninstall'
DEFAULTS_HELPER = '/usr/local/libexec/callas-defaults'
WIDGET_HELPER = '/usr/local/libexec/callas-widget'
DEFAULT_ICONS = Path('/usr/local/share/callas-os/default-app-icons.json')
ID = 'io.github.Callas157.AtualizadorDoSistema'
CRITICAL = ('linux', 'linux-lts', 'linux-zen', 'linux-hardened', 'systemd', 'glibc',
            'nvidia-utils', 'nvidia-open-dkms', 'mesa', 'linux-firmware')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)')

# The optional app is a separate download, never part of the OS install stage.
CODEX_REF = 'd71a0e916c545c845c8991d7365a8771ced99c81'
CODEX_SHA256 = 'f1ed256b4b0542e1142f69887c752336c3500531df937cd3d96e51e49f1eb134'
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
    if action.startswith('nvidia:'):
        return [NVIDIA_HELPER, '--nvidia-select', action.split(':', 1)[1]]
    if action == 'callas': return ['/usr/local/libexec/callas-release']
    raise ValueError('Função desconhecida')

def option_icon(name):
    if name == 'codex':
        pixmap = QPixmap(); pixmap.loadFromData(CODEX_ICON.encode(), 'SVG')
        return QIcon(pixmap)
    paths = {
        'edit-delete': '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
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
        self.choices = QVBoxLayout()
        layout.addLayout(self.choices)
        layout.addWidget(self.message)
        layout.addStretch()
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

    def select(self, name, confirmed=False):
        if self.worker is not None: return
        if not confirmed:
            text = f'Definir {name} como principal para o painel, notificações e login?'
            if getattr(self, 'controller', None):
                self.controller.confirm_action('Definir monitor principal', text, lambda: self.select(name, True), 'Aplicar'); return
            if QMessageBox.question(self, 'Definir monitor principal', text) != QMessageBox.Yes: return
        self.message.setText('Aplicando configuração. Autorize o ajuste do login quando solicitado…')
        self.execute(['--set-primary', name, '--expected', json.dumps([o['name'] for o in self.snapshot]),
                      '--gui-auth'], self.applied)

    def applied(self, code, output, error):
        if code:
            self.message.setText('Não foi possível concluir. As etapas já confirmadas podem ter sido aplicadas. '
                                 'O backup foi preservado quando criado. Atualize a lista para conferir.')
            if getattr(self, 'controller', None): self.message.setText(self.message.text() + '\n' + (error + '\n' + output).strip())
            else: QMessageBox.warning(self, 'Monitores', (error + '\n' + output).strip())
        else:
            self.detect()
            if getattr(self, 'controller', None): self.message.setText('Monitor principal configurado. Confira o login na próxima entrada.\n' + self.message.text())
            else: QMessageBox.information(self, 'Monitores', 'Monitor principal configurado. Confira o login na próxima entrada.')

    def reject(self):
        if self.worker is None: super().reject()

    def closeEvent(self, event):
        if self.worker is not None: event.ignore()
        else: event.accept()

def default_app_icon(name, fallback=True):
    try:
        data = json.loads(DEFAULT_ICONS.read_text())
        raw = base64.b64decode(data['icons'][name], validate=True)
        pixmap = QPixmap()
        if pixmap.loadFromData(raw, 'PNG'): return QIcon(pixmap)
    except (OSError, ValueError, KeyError): pass
    return QIcon.fromTheme(name, option_icon('applications-all') if fallback else QIcon())


def application_icon(app):
    if app.get('kind') == 'codex': return option_icon('codex')
    name = app.get('icon', '')
    if name and Path(name).is_absolute():
        icon = QIcon(name)
        if not icon.isNull(): return icon
    candidates = [name]
    if app.get('kind', '').startswith('flatpak'):
        fields = app.get('id', '').split('/')
        if len(fields) > 1: candidates.append(fields[1])
    else: candidates.append(app.get('id', '').removesuffix('-bin'))
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    roots = [data / 'icons/hicolor', data / 'flatpak/exports/share/icons/hicolor',
             Path('/var/lib/flatpak/exports/share/icons/hicolor'), Path('/usr/share/icons/hicolor')]
    for candidate in candidates:
        if not re.fullmatch(r'[a-zA-Z0-9_.+\-]+', candidate): continue
        icon = default_app_icon(candidate, fallback=False)
        if not icon.isNull(): return icon
        for root in roots:
            for size in ('64x64', '128x128', '256x256', 'scalable', '48x48', '32x32'):
                for suffix in ('.png', '.svg', '.xpm'):
                    path = root / size / 'apps' / (candidate + suffix)
                    if path.is_file():
                        icon = QIcon(str(path))
                        if not icon.isNull(): return icon
    return option_icon('applications-all')


class ClockConfigPage(QWidget):
    CORNERS = {'top-left': ('↖', 'Superior esquerdo'), 'top-right': ('↗', 'Superior direito'),
               'bottom-left': ('↙', 'Inferior esquerdo'), 'bottom-right': ('↘', 'Inferior direito')}

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner; self.corner_buttons = {}
        layout = QVBoxLayout(self); layout.setContentsMargins(26, 24, 26, 24)
        layout.addWidget(QLabel('Configurar Relógio Moderno', objectName='title'))
        intro = QLabel('Clique em um dos quatro cantos do monitor desejado para mover o relógio.\n'
                       'Você também pode arrastar e redimensionar livremente pelo modo de edição da área de trabalho.')
        intro.setWordWrap(True); layout.addWidget(intro)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self.monitors = QWidget(); self.grid = QGridLayout(self.monitors); self.grid.setAlignment(Qt.AlignTop)
        self.grid.setSpacing(16); scroll.setWidget(self.monitors); layout.addWidget(scroll, 1)
        self.status = QLabel('Detectando monitores…'); self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText); layout.addWidget(self.status)
        controls = QHBoxLayout()
        refresh = QPushButton('Atualizar monitores'); refresh.clicked.connect(self.refresh); controls.addWidget(refresh)
        self.edit = QPushButton('Mover livremente'); self.edit.clicked.connect(self.edit_desktop); controls.addWidget(self.edit)
        controls.addStretch()
        self.back = QPushButton('Voltar'); self.back.clicked.connect(owner.close_clock_config); controls.addWidget(self.back)
        layout.addLayout(controls)

    def clear_monitors(self):
        self.corner_buttons = {}
        while self.grid.count(): self.grid.takeAt(0).widget().deleteLater()

    def refresh(self):
        self.clear_monitors(); self.status.setText('Detectando monitores…')
        def loaded(code, output, error):
            try:
                if code: raise RuntimeError(error or 'Não foi possível detectar as telas.')
                screens = json.loads(output)
                if not isinstance(screens, list) or not screens: raise ValueError('Nenhum monitor ativo encontrado.')
                names = set()
                for screen in screens:
                    if (not isinstance(screen, dict) or not isinstance(screen.get('name'), str)
                            or not screen['name'] or screen['name'] in names): raise ValueError('Lista de monitores inválida.')
                    names.add(screen['name'])
                for index, screen in enumerate(screens): self.add_monitor(index, screen)
                self.status.setText('Escolha um canto. A posição só muda quando você clicar.')
            except (ValueError, TypeError, RuntimeError) as exc:
                self.clear_monitors(); self.status.setText(str(exc))
        self.owner.run_helper(['--screens'], False, loaded, helper=WIDGET_HELPER)

    def add_monitor(self, index, screen):
        card = QFrame(objectName='card'); box = QVBoxLayout(card)
        name = screen['name']; title = QLabel(f'Monitor {index+1} · {name}')
        title.setTextFormat(Qt.PlainText); box.addWidget(title)
        preview = QFrame(); preview.setObjectName('monitorPreview'); preview.setMinimumHeight(205)
        preview.setStyleSheet('QFrame#monitorPreview { border: 2px solid #71859b; border-radius: 8px; background: #19232f; }')
        corners = QGridLayout(preview); corners.setContentsMargins(12,12,12,12)
        for corner, (symbol, text) in self.CORNERS.items():
            button = QPushButton(symbol); button.setFixedSize(48,48)
            button.setStyleSheet('font-size: 25px;')
            button.setToolTip(text); button.setAccessibleName(f'Monitor {index+1} {name}: {text}')
            button.clicked.connect(lambda checked=False, connector=name, position=corner: self.move(connector,position))
            corners.addWidget(button, 0 if corner.startswith('top') else 2, 0 if corner.endswith('left') else 2)
            self.corner_buttons[(name,corner)] = button
        label = QLabel(f"{screen.get('width','?')} × {screen.get('height','?')}\nClique em um canto")
        label.setAlignment(Qt.AlignCenter); label.setWordWrap(True); corners.addWidget(label,1,0,1,3)
        corners.setRowStretch(1,1); corners.setColumnStretch(1,1)
        box.addWidget(preview); self.grid.addWidget(card,index//2,index%2)

    def move(self, connector, corner):
        self.status.setText('Movendo o relógio…')
        def moved(code, output, error):
            self.status.setText((f'Relógio movido para {connector}: {self.CORNERS[corner][1].lower()}.' if code == 0
                                 else error or output or 'Não foi possível mover o relógio.'))
        self.owner.run_helper(['--move',connector,corner], False, moved, helper=WIDGET_HELPER)

    def edit_desktop(self):
        def opened(code, output, error):
            self.status.setText('Modo de edição aberto. Arraste o relógio na área de trabalho.' if code == 0
                                else error or output or 'Não foi possível abrir o modo de edição.')
        self.owner.run_helper(['--edit'], False, opened, helper=WIDGET_HELPER)


class NativeAppsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Aplicativos nativos — Central Callas OS')
        self.resize(760, 360); self.setMinimumWidth(690)
        self.process = None; self.busy = False; self.apps = []; self.checks = {}; self.card_widgets = []
        self.catalog_loaded = False; self.refreshing_after_install = False
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0)
        self.stack = QStackedWidget(); root.addWidget(self.stack)
        self.content = QWidget(); self.stack.addWidget(self.content); self.clock_page = None
        layout = QVBoxLayout(self.content); layout.setContentsMargins(26, 24, 26, 24); layout.setSpacing(14)
        layout.addWidget(QLabel('Aplicativos nativos', objectName='title'))
        self.menu = QWidget(); menu = QHBoxLayout(self.menu); menu.setContentsMargins(0, 0, 0, 0)
        self.defaults_button = QPushButton(option_icon('applications-all'), 'Aplicativos padrão Callas OS')
        self.update_button = QPushButton(option_icon('system-software-update'), 'Atualizar aplicativos')
        for button in (self.defaults_button, self.update_button): button.setMinimumHeight(78); menu.addWidget(button)
        self.defaults_button.clicked.connect(self.show_defaults); self.update_button.clicked.connect(self.update_apps)
        layout.addWidget(self.menu)
        self.catalog_panel = QWidget(); panel = QVBoxLayout(self.catalog_panel); panel.setContentsMargins(0, 0, 0, 0)
        intro = QLabel('Restaure somente os aplicativos que você escolher. Desmarcar não desinstala.\n'
                       'Tamanhos não incluem todas as dependências; configurações e dados pessoais são preservados.')
        intro.setWordWrap(True); panel.addWidget(intro)
        self.search = QLineEdit(); self.search.setPlaceholderText('Buscar aplicativos padrão…')
        self.search.textChanged.connect(self.filter_cards); panel.addWidget(self.search)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.cards = QWidget(); self.grid = QGridLayout(self.cards); self.grid.setAlignment(Qt.AlignTop)
        self.grid.setSpacing(12); self.scroll.setWidget(self.cards); panel.addWidget(self.scroll, 1)
        selection = QHBoxLayout()
        self.select_all = QPushButton('Selecionar disponíveis'); self.select_all.clicked.connect(lambda: self.select_available(True))
        self.clear = QPushButton('Desmarcar todos'); self.clear.clicked.connect(lambda: self.select_available(False))
        self.install_selected = QPushButton('Instalar selecionados'); self.install_selected.setObjectName('install')
        self.install_selected.clicked.connect(self.install_checked)
        selection.addWidget(self.select_all); selection.addWidget(self.clear); selection.addStretch(); selection.addWidget(self.install_selected)
        panel.addLayout(selection)
        self.catalog_panel.hide(); layout.addWidget(self.catalog_panel, 1)
        self.status = QLabel('Escolha os aplicativos padrão ou atualize os aplicativos já instalados.')
        self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText); layout.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setTextVisible(False); self.progress.hide()
        layout.addWidget(self.progress)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMaximumBlockCount(4000)
        self.details.setMaximumHeight(125); self.details.hide(); layout.addWidget(self.details)
        footer = QHBoxLayout()
        self.reload = QPushButton('Consultar versões e tamanhos'); self.reload.clicked.connect(self.refresh); self.reload.hide()
        self.back = QPushButton('Voltar'); self.back.clicked.connect(self.go_back)
        footer.addWidget(self.reload); footer.addStretch(); footer.addWidget(self.back); layout.addLayout(footer)
        self.setStyleSheet('QPushButton#install { background: #23824d; border: 1px solid #47b978; color: white; }'
                           'QPushButton#install:hover { background: #2d995e; }'
                           'QPushButton#install:disabled { background: #303945; color: #9ca8b5; border-color: #46515f; }'
                           'QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #91a4b7; border-radius: 3px; }'
                           'QCheckBox::indicator:checked { background: #39a967; border-color: #71df9b; }')

    def show_defaults(self):
        if self.busy: return
        self.catalog_panel.show(); self.reload.show()
        self.resize(self.parentWidget().size() if self.parentWidget() else QSize(940, 820))
        if not self.catalog_loaded: self.refresh()

    def update_apps(self):
        if self.busy: return
        host = getattr(self, 'controller', None) or self.parentWidget()
        self.accept()
        if host: host.start('nativos')

    def go_back(self):
        if self.busy: return
        if self.clock_page is not None and self.stack.currentWidget() is self.clock_page:
            self.close_clock_config(); return
        if self.catalog_panel.isVisible():
            self.catalog_panel.hide(); self.reload.hide(); self.details.hide(); self.resize(760, 360)
            self.status.setText('Escolha os aplicativos padrão ou atualize os aplicativos já instalados.')
        else: self.reject()

    def selected_ids(self): return [key for key, check in self.checks.items() if check.isChecked()]

    def selection_changed(self):
        count = len(self.selected_ids())
        self.install_selected.setText(f'Instalar selecionados ({count})')
        self.install_selected.setEnabled(count > 0 and not self.busy)

    def select_available(self, checked):
        if self.busy: return
        for check in self.checks.values():
            if check.isEnabled(): check.setChecked(checked)

    def filter_cards(self, *_):
        query = self.search.text().casefold().strip(); visible = 0
        for app, card in self.card_widgets:
            show = query in (app['title'] + ' ' + app['name'] + ' ' + app['description']).casefold()
            card.setVisible(show)
            self.grid.removeWidget(card)
            if show:
                self.grid.addWidget(card, visible // 2, visible % 2); visible += 1

    def render_cards(self):
        selected = set(self.selected_ids())
        for _, card in self.card_widgets: card.deleteLater()
        self.checks = {}; self.card_widgets = []
        while self.grid.count(): self.grid.takeAt(0)
        for i, app in enumerate(self.apps):
            card = QFrame(objectName='card'); box = QVBoxLayout(card); box.setContentsMargins(15, 14, 15, 14)
            header = QHBoxLayout()
            icon = QLabel(); icon.setPixmap(default_app_icon(app['icon']).pixmap(44, 44)); header.addWidget(icon)
            title = QLabel(app['title']); title.setTextFormat(Qt.PlainText)
            title.setStyleSheet('font-size: 17px; font-weight: 600;'); header.addWidget(title, 1)
            check = QCheckBox(); check.setAccessibleName('Selecionar ' + app['title'])
            check.setEnabled(not app['installed']); check.setChecked(app['id'] in selected and not app['installed'])
            self.checks[app['id']] = check; check.toggled.connect(self.selection_changed); header.addWidget(check); box.addLayout(header)
            source = {'repo': 'Nativo', 'aur': 'AUR', 'flatpak': 'Flatpak de sistema', 'plasmoid': 'Widget do Plasma'}[app['source']]
            description = QLabel(app['description']); description.setTextFormat(Qt.PlainText); description.setWordWrap(True); box.addWidget(description)
            size_label = 'Instalado' if app['installed'] else 'Após instalar'
            info = QLabel(f"{source} · {'Instalado' if app['installed'] else 'Disponível para instalar'}\n"
                          f"Versão: {app['version']}\n{size_label}: {app['size']} · Download: {app['download']}")
            info.setTextFormat(Qt.PlainText); info.setWordWrap(True); box.addWidget(info)
            if app.get('notice'):
                note = QLabel(app['notice']); note.setWordWrap(True); note.setTextFormat(Qt.PlainText)
                note.setStyleSheet('color: #b7c4d2; font-size: 12px;'); box.addWidget(note)
            box.addStretch()
            install = QPushButton('Instalado' if app['installed'] else 'Instalar'); install.setObjectName('install')
            install.setMinimumHeight(42)
            install.setEnabled(not app['installed']); install.clicked.connect(lambda checked=False, key=app['id']: self.install_ids([key]))
            actions = QHBoxLayout(); actions.addWidget(install, 1)
            if app['source'] == 'plasmoid':
                configure = QPushButton('Configurar'); configure.setEnabled(app['installed'])
                configure.setMinimumHeight(42)
                configure.clicked.connect(self.show_clock_config); actions.addWidget(configure, 1)
            box.addLayout(actions); self.grid.addWidget(card, i // 2, i % 2); self.card_widgets.append((app, card))
        self.filter_cards(); self.selection_changed()

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.menu, self.cards, self.search, self.select_all, self.clear, self.reload, self.back): widget.setEnabled(not busy)
        self.progress.setVisible(busy); self.selection_changed()
        if self.clock_page is not None: self.clock_page.setEnabled(not busy)

    def show_clock_config(self):
        if self.busy or not any(app['source'] == 'plasmoid' and app['installed'] for app in self.apps): return
        if self.clock_page is None:
            self.clock_page = ClockConfigPage(self); self.stack.addWidget(self.clock_page)
        self.stack.setCurrentWidget(self.clock_page); self.clock_page.refresh()

    def close_clock_config(self):
        if not self.busy: self.stack.setCurrentWidget(self.content)

    def run_helper(self, args, privileged, callback, *, helper=None):
        if self.process is not None: return
        helper = helper or DEFAULTS_HELPER
        if not Path(helper).is_file():
            callback(1, '', 'Execute Callas OS Update para disponibilizar esta função.'); return
        self.set_busy(True)
        process = QProcess(self); self.process = process
        output = bytearray(); error = bytearray(); finished_once = False
        env = QProcessEnvironment.systemEnvironment(); env.remove('CALLAS_KERNEL_UPDATE_CONTEXT')
        env.insert('PYTHONUNBUFFERED', '1')
        env.insert('SUDO_ASKPASS', str(Path(__file__).resolve().with_name('callas-update-askpass')))
        process.setProcessEnvironment(env)
        def read_stdout():
            data = bytes(process.readAllStandardOutput()); output.extend(data)
            if privileged: self.details.insertPlainText(data.decode('utf-8', 'replace'))
        def read_stderr():
            data = bytes(process.readAllStandardError()); error.extend(data)
            if privileged: self.details.insertPlainText(data.decode('utf-8', 'replace'))
        process.readyReadStandardOutput.connect(read_stdout); process.readyReadStandardError.connect(read_stderr)
        def finished(code, *_):
            nonlocal finished_once
            if finished_once: return
            finished_once = True; read_stdout(); read_stderr()
            self.process = None; process.deleteLater(); self.set_busy(False)
            callback(code, output.decode('utf-8', 'replace'), error.decode('utf-8', 'replace'))
        process.finished.connect(finished)
        process.errorOccurred.connect(lambda value: finished(1) if value == QProcess.FailedToStart else None)
        argv = [helper, *args]
        if privileged: argv = ['/usr/bin/sudo', '-A', '--', *argv]
        process.start(argv[0], argv[1:]); process.closeWriteChannel()

    def refresh(self, *_ , message=''):
        if self.busy: return
        self.status.setText('Consultando aplicativos, versões e tamanhos…')
        def loaded(code, output, error):
            try:
                if code: raise RuntimeError(error or 'Não foi possível consultar o catálogo.')
                apps = json.loads(output)
                if not isinstance(apps, list): raise ValueError('Catálogo inválido')
                self.apps = apps; self.catalog_loaded = True; self.render_cards()
                self.status.setText(message or 'Marque os aplicativos desejados ou use o botão Instalar de cada cartão.')
            except (ValueError, RuntimeError) as exc:
                self.status.setText(str(exc))
                # Stale metadata never authorizes a new installation after failure.
                self.apps = []; self.render_cards(); self.catalog_loaded = False
        self.run_helper(['--list'], False, loaded)

    def install_checked(self): self.install_ids(self.selected_ids())

    def install_ids(self, ids, confirmed=False):
        if self.busy or not ids: return
        selected = [app for app in self.apps if app['id'] in ids and not app['installed']]
        if len(selected) != len(ids): return
        if not confirmed:
            question = QMessageBox(self); question.setWindowTitle('Instalar aplicativos padrão')
            question.setTextFormat(Qt.PlainText)
            question.setText('Instalar os aplicativos selecionados?\n\n' + '\n'.join(app['title'] for app in selected) +
                             '\n\nSomente estes aplicativos serão restaurados. A preferência de desinstalação será desfeita '
                             'após cada instalação confirmada. Pode ser necessária autorização administrativa.')
            question.setStandardButtons(QMessageBox.Yes | QMessageBox.No); question.setDefaultButton(QMessageBox.No)
            question.button(QMessageBox.Yes).setText('Instalar'); question.button(QMessageBox.No).setText('Cancelar')
            if getattr(self, 'controller', None):
                self.controller.confirm_action(question.windowTitle(), question.text(), lambda: self.install_ids(ids, True), 'Instalar')
                question.deleteLater(); return
            if question.exec() != QMessageBox.Yes: return
        self.details.clear(); self.details.show(); self.status.setText('Instalando os aplicativos selecionados…')
        def installed(code, output, error):
            logger = Path('/usr/local/libexec/callas-logs')
            if logger.is_file():
                try:
                    subprocess.run([str(logger), '--write', 'Aplicativos'],
                        input=('Restaurar: ' + ', '.join(ids) + f'\nCódigo: {code}\n' + output + '\n' + error).encode(),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                except (OSError, subprocess.SubprocessError): self.details.appendPlainText('Não foi possível salvar o log em Documentos.')
            message = ('Aplicativos selecionados instalados. Os demais foram preservados.' if code == 0 else
                       'Instalação não concluída para todos os itens. Consulte os detalhes; instalações confirmadas foram preservadas.')
            self.refresh(message=message)
        personal = [app['id'] for app in selected if app['source'] == 'plasmoid']
        packages = [app['id'] for app in selected if app['source'] != 'plasmoid']
        user = pwd.getpwuid(os.getuid()).pw_name
        if personal and packages:
            def packages_finished(code, output, error):
                def personal_finished(clock_code, clock_output, clock_error):
                    installed(code or clock_code, output+'\n'+clock_output, error+'\n'+clock_error)
                self.run_helper(['--restore', user, *personal], False, personal_finished)
            self.run_helper(['--restore', user, *packages], True, packages_finished)
        else:
            self.run_helper(['--restore', user, *ids], bool(packages), installed)

    def reject(self):
        if not self.busy: super().reject()

    def closeEvent(self, event):
        if self.busy: event.ignore()
        else: event.accept()


class UninstallDialog(QDialog):
    """Keep inventory and package-manager work off the GUI thread."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Desinstalar aplicativos — Central Callas OS')
        self.resize(parent.size() if parent else QSize(900, 770))
        self.setMinimumSize(690, 620)
        self.apps = []
        self.process = None
        self._output = bytearray()
        self._error = bytearray()
        self.busy = False
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 25, 28, 24); layout.setSpacing(14)
        layout.addWidget(QLabel('Desinstalar aplicativos', objectName='title'))
        intro = QLabel('Escolha um aplicativo para remover. Seus arquivos pessoais serão preservados.\n'
                       'Componentes essenciais ficam protegidos; dependências não são removidas em cascata.')
        intro.setWordWrap(True); layout.addWidget(intro)
        self.search = QLineEdit(); self.search.setPlaceholderText('Buscar por nome, pacote ou origem…')
        self.search.textChanged.connect(self.filter_apps); layout.addWidget(self.search)
        self.protected = QCheckBox('Mostrar componentes protegidos (somente consulta)')
        self.protected.toggled.connect(self.filter_apps); layout.addWidget(self.protected)
        self.table = QTableWidget(0, 4)
        self.table.setIconSize(QSize(32, 32)); self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setHorizontalHeaderLabels(['Aplicativo', 'Origem', 'Versão', 'Situação'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.table, 1)
        self.info = QLabel(''); self.info.setWordWrap(True); self.info.setTextFormat(Qt.PlainText)
        layout.addWidget(self.info)
        self.status = QLabel(''); self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(3000); self.details.setMaximumHeight(140); self.details.hide()
        layout.addWidget(self.details)
        row = QHBoxLayout()
        self.reload = QPushButton('Atualizar lista'); self.reload.clicked.connect(self.refresh)
        self.back = QPushButton('Voltar'); self.back.clicked.connect(self.reject)
        self.remove = QPushButton('Desinstalar'); self.remove.setObjectName('primary')
        self.remove.setIcon(option_icon('edit-delete')); self.remove.clicked.connect(self.uninstall)
        row.addWidget(self.reload); row.addStretch(); row.addWidget(self.back); row.addWidget(self.remove)
        layout.addLayout(row)
        QTimer.singleShot(0, self.refresh)

    def selected(self):
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.UserRole) if row >= 0 and self.table.item(row, 0) else None

    def selection_changed(self):
        app = self.selected()
        self.remove.setEnabled(bool(app) and not app['blocked'] and not self.busy)
        self.info.setText((app['id'] + '\n' + app['reason']) if app else 'Selecione um aplicativo para ver os detalhes.')

    def filter_apps(self, *_):
        selected = self.selected()
        query = self.search.text().casefold().strip()
        visible = [app for app in self.apps if (self.protected.isChecked() or not app['blocked'])
                   and query in (app['name'] + ' ' + app['id'] + ' ' + app['source']).casefold()]
        self.table.setRowCount(0)
        for app in visible:
            row = self.table.rowCount(); self.table.insertRow(row)
            for col, value in enumerate((app['name'], app['source'], app.get('version', ''),
                                         'Protegido' if app['blocked'] else 'Aplicativo')):
                item = QTableWidgetItem(value); item.setToolTip(app['reason'])
                if col == 0:
                    item.setData(Qt.UserRole, app); item.setIcon(application_icon(app))
                self.table.setItem(row, col, item)
            if selected and (app['kind'], app['id']) == (selected['kind'], selected['id']):
                self.table.selectRow(row)
        self.selection_changed()

    def set_busy(self, busy):
        self.busy = busy
        self.reload.setEnabled(not busy); self.back.setEnabled(not busy)
        self.table.setEnabled(not busy); self.search.setEnabled(not busy); self.protected.setEnabled(not busy)
        self.progress.setVisible(busy); self.selection_changed()

    def run_helper(self, args, privileged, callback):
        if self.process is not None: return
        if not Path(UNINSTALL_HELPER).is_file():
            self.status.setText('Atualize a Central pelo Callas OS Update para instalar o auxiliar de desinstalação.')
            self.set_busy(False); return
        self.set_busy(True)
        process = QProcess(self); self.process = process
        self._output = bytearray(); self._error = bytearray()
        env = QProcessEnvironment.systemEnvironment()
        env.remove('CALLAS_KERNEL_UPDATE_CONTEXT')
        env.insert('PYTHONUNBUFFERED', '1')
        env.insert('SUDO_ASKPASS', str(Path(__file__).resolve().with_name('callas-update-askpass')))
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(lambda: self._output.extend(bytes(process.readAllStandardOutput())))
        process.readyReadStandardError.connect(lambda: self._error.extend(bytes(process.readAllStandardError())))
        done = False
        def finished(code, *_):
            nonlocal done
            if done: return
            done = True
            self._output.extend(bytes(process.readAllStandardOutput()))
            self._error.extend(bytes(process.readAllStandardError()))
            output = self._output.decode('utf-8', 'replace'); error = self._error.decode('utf-8', 'replace')
            self.process = None; process.deleteLater(); self.set_busy(False)
            callback(code, output, error)
        process.finished.connect(finished)
        process.errorOccurred.connect(lambda error: finished(1) if error == QProcess.FailedToStart else None)
        argv = [UNINSTALL_HELPER, *args]
        if privileged: argv = ['/usr/bin/sudo', '-A', '--', *argv]
        process.start(argv[0], argv[1:])
        process.closeWriteChannel()

    def refresh(self, *_ , message=''):
        if self.busy: return
        self.status.setText('Identificando aplicativos instalados…')
        def loaded(code, output, error):
            try:
                if code: raise RuntimeError(error or 'Não foi possível consultar os aplicativos.')
                apps = json.loads(output)
                if not isinstance(apps, list): raise ValueError('Lista de aplicativos inválida.')
                self.apps = apps; self.filter_apps()
                count = sum(not app['blocked'] for app in apps)
                self.status.setText((message + '\n' if message else '') + f'{count} aplicativos disponíveis. Componentes protegidos ficam ocultos.')
            except (ValueError, RuntimeError) as exc:
                self.apps = []; self.filter_apps(); self.status.setText(str(exc))
        self.run_helper(['--list'], False, loaded)

    def uninstall(self, confirmed=False):
        app = self.selected()
        if self.busy or not app: return
        if app['blocked']:
            self.status.setText(app['reason']); return
        admin = app['kind'] in ('native', 'flatpak-system')
        if not confirmed:
            confirmation = QMessageBox(self)
            confirmation.setWindowTitle('Confirmar desinstalação'); confirmation.setTextFormat(Qt.PlainText)
            confirmation.setText(f"Desinstalar {app['name']}?\n\nOrigem: {app['source']}\n{app['id']}\n\n"
                                 'Feche o aplicativo antes de continuar. Seus dados pessoais serão preservados.\n'
                                 'O Callas OS Update respeitará esta escolha.' +
                                 ('\nA autorização administrativa será solicitada se necessário.' if admin else ''))
            confirmation.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            confirmation.setDefaultButton(QMessageBox.No)
            confirmation.button(QMessageBox.Yes).setText('Desinstalar')
            confirmation.button(QMessageBox.No).setText('Cancelar')
            if getattr(self, 'controller', None):
                self.controller.confirm_action(confirmation.windowTitle(), confirmation.text(), lambda: self.uninstall(True), 'Desinstalar')
                confirmation.deleteLater(); return
            if confirmation.exec() != QMessageBox.Yes: return
        self.details.clear(); self.details.show()
        self.status.setText('Desinstalando ' + app['name'] + '…')
        def removed(code, output, error):
            self.details.setPlainText((output + '\n' + error).strip())
            logger = Path('/usr/local/libexec/callas-logs')
            if logger.is_file():
                try:
                    log = f"Desinstalar: {app['name']} | {app['kind']} | {app['id']}\nCódigo: {code}\n{output}\n{error}"
                    subprocess.run([str(logger), '--write', 'Aplicativos'], input=log.encode(),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                except (OSError, subprocess.SubprocessError):
                    self.details.appendPlainText('Não foi possível salvar o log em Documentos.')
            if code:
                self.status.setText('Desinstalação não concluída. A autorização pode ter sido cancelada. Veja os detalhes.')
                if not getattr(self, 'controller', None):
                    QMessageBox.warning(self, 'Desinstalação não concluída', error or output or 'Não foi possível iniciar a operação.')
            else:
                self.refresh(message=app['name'] + ' desinstalado. Dados pessoais preservados.')
        self.run_helper(['--remove', app['kind'], app['id']], admin, removed)

    def reject(self):
        if not self.busy: super().reject()

    def closeEvent(self, event):
        if self.busy:
            self.status.setText('Aguarde a operação terminar antes de fechar esta janela.'); event.ignore()
        else: event.accept()


class NvidiaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self.current = ''
        self.fixed = ''
        self.coherent = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 25, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(QLabel('Driver NVIDIA', objectName='title'))
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(QLabel('Versões com pacotes Open DKMS no arquivo oficial do Arch'))
        self.versions = QComboBox()
        self.versions.currentIndexChanged.connect(self.update_button)
        layout.addWidget(self.versions)
        layout.addStretch()
        row = QHBoxLayout()
        self.reload = QPushButton('Atualizar lista')
        self.reload.clicked.connect(self.refresh)
        self.back = QPushButton('Voltar')
        self.back.clicked.connect(self.reject)
        self.apply = QPushButton('Aplicar e fixar')
        self.apply.setObjectName('primary')
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.choose)
        row.addWidget(self.reload)
        row.addStretch()
        row.addWidget(self.back)
        row.addWidget(self.apply)
        layout.addLayout(row)
        QTimer.singleShot(0, self.refresh)

    def update_button(self, *_):
        version = self.versions.currentData()
        self.apply.setEnabled(not self.busy and bool(version) and
                              (version != self.fixed if self.coherent else version == self.fixed))

    def refresh(self):
        self.busy = True
        self.reload.setEnabled(False)
        self.back.setEnabled(False)
        self.versions.clear()
        self.update_button()
        self.status.setText('Consultando o arquivo oficial e os pacotes instalados…')
        process = QProcess(self)

        def finish(code, *_):
            self.busy = False
            self.reload.setEnabled(True)
            self.back.setEnabled(True)
            error = bytes(process.readAllStandardError()).decode('utf-8', 'replace').strip()
            try:
                if code:
                    raise ValueError(error or 'Não consegui iniciar o auxiliar NVIDIA.')
                state = json.loads(bytes(process.readAllStandardOutput()))
                self.current, self.fixed = state['installed'], state['fixed']
                self.coherent = state['coherent']
                self.status.setText(f'Instalado {self.current} · Fixado {self.fixed}')
                if not self.coherent:
                    self.status.setText(self.status.text() + '\nPilha divergente. Selecione a versão fixada para reparar.')
                self.versions.addItem('Selecione uma versão', None)
                for version in state['versions']:
                    label = version + (' (padrão para jogos)' if version == '610.57.04' else '')
                    self.versions.addItem(label, version)
                if self.fixed in state['versions']:
                    self.versions.setCurrentIndex(self.versions.findData(self.fixed))
                if state.get('error'):
                    self.status.setText(self.status.text() + '\n' + state['error'])
            except (ValueError, KeyError, TypeError) as exc:
                self.status.setText(str(exc))
            self.update_button()
            process.deleteLater()

        process.finished.connect(finish)
        process.errorOccurred.connect(lambda error: finish(1) if error == QProcess.FailedToStart else None)
        process.start(NVIDIA_HELPER, ['--nvidia-list'])

    def choose(self):
        version = self.versions.currentData()
        if not self.apply.isEnabled():
            return
        self.controller.confirm_action(
            'Trocar o driver NVIDIA',
            f'Aplicar e fixar a versão {version}? A Central testa a compilação nos kernels padrão e LTS '
            'antes da troca. Feche os jogos e salve seu trabalho. Após a validação, reinicie para carregar o driver.',
            lambda: self.controller.start('nvidia:' + version, True), 'Aplicar e fixar')

    def reject(self):
        if not self.busy:
            super().reject()


class MaintenanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 25, 28, 24); layout.setSpacing(16)
        layout.addWidget(QLabel('Limpeza e manutenção', objectName='title'))
        layout.addWidget(QLabel('Escolha a função de manutenção'))
        grid = QGridLayout(); layout.addLayout(grid)
        options = [('Limpeza segura', 'edit-clear', 'clean'),
            ('Espaço, backups e VMs', 'folder-open', 'report'),
            ('Verificar pacotes órfãos', 'applications-all', 'orphans'),
            ('Reaplicar modo manual', 'appointment-soon', 'repair'),
            ('Diagnóstico de jogo', 'view-list-details', 'games'),
            ('Atualizar Flatpaks', 'system-software-update', 'flatpaks')]
        for i, (title, icon, action) in enumerate(options):
            button = QPushButton(option_icon(icon), title); button.setMinimumHeight(68)
            button.clicked.connect(lambda checked=False, a=action: self.choose(a))
            grid.addWidget(button, i // 2, i % 2)
        layout.addStretch()
        back = QPushButton('Voltar à Central'); back.clicked.connect(self.reject)
        layout.addWidget(back, alignment=Qt.AlignRight)

    def choose(self, action):
        host = getattr(self, 'controller', None) or self.parentWidget()
        self.accept(); host.start(action)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.active_page = None
        self.pending_confirmation = None
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
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget(); root.addWidget(self.pages)
        self.home_page = QWidget(); self.pages.addWidget(self.home_page)
        self.confirm_page = QWidget(); self.pages.addWidget(self.confirm_page)
        confirmation = QVBoxLayout(self.confirm_page)
        confirmation.setContentsMargins(32, 28, 32, 28); confirmation.setSpacing(20)
        self.confirm_title = QLabel('', objectName='title'); self.confirm_title.setWordWrap(True)
        self.confirm_text = QLabel(''); self.confirm_text.setTextFormat(Qt.PlainText); self.confirm_text.setWordWrap(True)
        confirmation.addWidget(self.confirm_title); confirmation.addWidget(self.confirm_text); confirmation.addStretch()
        row = QHBoxLayout(); row.addStretch()
        self.confirm_cancel = QPushButton('Cancelar'); self.confirm_cancel.clicked.connect(lambda: self.finish_confirmation(False))
        self.confirm_yes = QPushButton('Continuar'); self.confirm_yes.setObjectName('primary')
        self.confirm_yes.clicked.connect(lambda: self.finish_confirmation(True))
        row.addWidget(self.confirm_cancel); row.addWidget(self.confirm_yes); confirmation.addLayout(row)
        self.pages.setCurrentWidget(self.home_page)
        layout = QVBoxLayout(self.home_page)
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
            ('Aplicativos nativos', 'applications-all', self.native_apps),
            ('Monitores', 'video-display', self.monitors),
            ('Atualizar geral', 'system-software-update', lambda: self.start('sistema')),
            ('Callas OS Update', 'system-upgrade', lambda: self.start('callas')),
            ('Codex', 'codex', self.codex),
            ('Desinstalar aplicativos', 'edit-delete', self.uninstall_apps),
            ('Driver NVIDIA', 'video-display', self.nvidia),
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
        rl.addWidget(QLabel('Atualização concluída. Deseja reiniciar agora?'))
        rr = QHBoxLayout(); rr.addStretch()
        reboot = self.button('Reiniciar agora', 'system-reboot', self.restart)
        reboot.setObjectName('primary'); rr.addWidget(reboot)
        rr.addWidget(self.button('Mais tarde', 'appointment-soon', self.defer_reboot))
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

    def operation_busy(self):
        page = self.active_page
        return (self.process is not None or (page is not None and
                (getattr(page, 'busy', False) or getattr(page, 'worker', None) is not None)))

    def open_page(self, page_type):
        if self.operation_busy() or self.pending_confirmation: return None
        if self.active_page is not None:
            if isinstance(self.active_page, page_type): return self.active_page
            self.return_home(self.active_page)
        page = page_type(self)
        page.controller = self
        page.setWindowFlags(Qt.Widget)
        page.accepted.connect(lambda: self.return_home(page))
        page.rejected.connect(lambda: self.return_home(page))
        self.pages.addWidget(page); self.active_page = page
        self.pages.setCurrentWidget(page)
        return page

    def return_home(self, page=None):
        if self.operation_busy() or self.pending_confirmation: return
        if page is not None and page is not self.active_page: return
        page = self.active_page
        self.pages.setCurrentWidget(self.home_page); self.active_page = None
        self.monitor_dialog = None
        if page is not None:
            self.pages.removeWidget(page); page.deleteLater()

    def confirm_action(self, title, text, callback, affirmative='Continuar'):
        if self.pending_confirmation or self.operation_busy(): return
        self.confirm_title.setText(title); self.confirm_text.setText(text)
        self.confirm_yes.setText(affirmative)
        self.pending_confirmation = (self.pages.currentWidget(), callback)
        self.pages.setCurrentWidget(self.confirm_page); self.confirm_cancel.setFocus()

    def finish_confirmation(self, accepted):
        pending = self.pending_confirmation
        if not pending: return
        previous, callback = pending; self.pending_confirmation = None
        self.pages.setCurrentWidget(previous)
        if accepted: callback()

    def maintenance(self): self.open_page(MaintenanceDialog)

    def monitors(self):
        page = self.open_page(MonitorDialog)
        if page is not None: self.monitor_dialog = page

    def native_apps(self): self.open_page(NativeAppsDialog)

    def uninstall_apps(self): self.open_page(UninstallDialog)

    def nvidia(self): self.open_page(NvidiaDialog)

    def codex(self, confirmed=False):
        if self.process is not None: return
        launcher = codex_launcher()
        if launcher.is_file() and os.access(launcher, os.X_OK):
            try: subprocess.Popen([str(launcher)], start_new_session=True)
            except OSError as exc: self.status.setText('Codex: ' + str(exc))
            return
        if not confirmed:
            self.confirm_action('Instalar Codex',
                'Baixar e instalar Codex no seu perfil e adicioná-lo ao menu KDE?\n\n'
                'O ditado baixa um modelo de voz de aproximadamente 1,5 GB. '
                'Depois, entre com sua própria conta ChatGPT. '
                'O sistema pedirá senha somente se faltar alguma dependência.',
                lambda: self.codex(True), 'Instalar')
            return
        self.start('codex')

    def start(self, action, confirmed=False):
        if self.operation_busy() or self.pending_confirmation: return
        self.return_home()
        command = action_command(action)
        if not Path(command[0]).is_file():
            self.stage.setText('Função indisponível'); self.status.setText('O auxiliar desta função não está instalado: ' + command[0]); return
        if not confirmed and action in ('sistema', 'repair'):
            title, text = (('Atualizar geral', 'Atualizar o sistema e os aplicativos? Esta função inclui kernel, com as proteções existentes do Callas OS.')
                if action == 'sistema' else ('Atualizações manuais', 'Desativar os agendamentos de atualização e manter somente os botões manuais da Central?'))
            self.confirm_action(title, text, lambda: self.start(action, True)); return
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
        if action in ('games', 'orphans') or action.startswith('nvidia:'):
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
            if self.action.startswith('nvidia:'):
                self.reboot_pending = True
                self.restart_panel.show()
                self.status.setText('Driver NVIDIA fixado e boot verificado. Reinicie para carregar a versão escolhida.')
            if self.action in ('sistema', 'nativos', 'callas', 'flatpaks'):
                self.reboot_pending = (self.action in ('sistema', 'callas') or
                                       reboot_needed(self.before, after, Path('/run/reboot-required').exists()))
                self.restart_panel.setVisible(self.reboot_pending)
                if self.action in ('sistema', 'callas'):
                    self.status.setText('Atualização concluída. Você pode reiniciar agora ou deixar para mais tarde.')
                elif after is None or self.before is None:
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

    def restart(self, confirmed=False):
        if not self.reboot_pending or self.process is not None: return
        if not confirmed:
            self.confirm_action('Reiniciar agora', 'Salvou seus arquivos? Reiniciar o computador agora?', lambda: self.restart(True), 'Reiniciar'); return
        result = subprocess.run(['/usr/bin/systemctl', 'reboot'], capture_output=True, text=True)
        if result.returncode: self.status.setText('Não foi possível reiniciar: ' + result.stderr)

    def open_logs(self):
        try:
            result = subprocess.run(['/usr/bin/xdg-user-dir', 'DOCUMENTS'], capture_output=True, text=True, timeout=5)
            documents = Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip().startswith('/') else Path.home() / 'Documentos'
            logs = documents / 'Callas OS' / 'Callas OS Logs'
            logs.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(['/usr/bin/xdg-open', str(logs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc: self.status.setText('Logs: ' + str(exc))

    def closeEvent(self, event):
        if self.operation_busy():
            self.status.setText('Aguarde a operação terminar antes de fechar a Central.')
            event.ignore()
        else: event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Central Callas OS'); app.setDesktopFileName(ID)
    if sys.argv[1:] == ['--askpass']:
        value, ok = QInputDialog.getText(None, 'Autorizar operação', 'Senha de administrador:', QLineEdit.Password)
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
        (QPalette.HighlightedText, '#ffffff'), (QPalette.PlaceholderText, '#aebac7')]: palette.setColor(role, QColor(color))
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
