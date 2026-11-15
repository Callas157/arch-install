#!/usr/bin/python3
"""Deploy the same updater ID for existing profiles and clean installations."""
import argparse
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile

ID = 'io.github.Callas157.AtualizadorDoSistema.desktop'
ICON = '''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><defs><linearGradient id="a" x2="0" y2="1"><stop stop-color="#70d5ff"/><stop offset="1" stop-color="#2878dc"/></linearGradient></defs><rect x="8" y="8" width="112" height="112" rx="29" fill="#243347"/><path d="M96 50A35 35 0 0 0 35 34l-9 12m0-20v20h20M32 78a35 35 0 0 0 61 16l9-12m0 20V82H82" fill="none" stroke="url(#a)" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/><path d="M64 86V48m-14 14 14-14 14 14" fill="none" stroke="#f2f8ff" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/></svg>'''

def atomic(path, data, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink(): raise ValueError('Destino simbólico: ' + str(path))
    fd, temporary = tempfile.mkstemp(prefix='.callas-update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)

def desktop(gui, icon):
    return f'''[Desktop Entry]
Type=Application
Name=Central Callas OS
Comment=Atualizações, manutenção e monitor principal
Exec=/usr/bin/python3 "{gui}"
TryExec=/usr/bin/python3
Icon={icon}
Terminal=false
Categories=System;
Keywords=atualizador;atualização;Arch;pacman;Flatpak;monitores;telas;central;
StartupNotify=true
StartupWMClass=io.github.Callas157.AtualizadorDoSistema
'''.encode()

def deploy(source, prefix):
    prefix = Path(prefix)
    for relative in ('lib', 'lib/callas-update', 'share', 'share/applications', 'share/icons',
                     'share/icons/hicolor', 'share/icons/hicolor/scalable', 'share/icons/hicolor/scalable/apps'):
        directory = prefix / relative
        if directory.is_symlink(): raise ValueError('Diretório simbólico: ' + str(directory))
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o755)
    folder = prefix / 'lib/callas-update'
    gui = folder / 'callas-update-gui.py'
    atomic(gui, Path(source).read_bytes(), 0o755)
    # sudo captures only this helper's stdout; passwords never enter the log PTY.
    helper = f'#!/bin/sh\nexec /usr/bin/python3 "{gui}" --askpass\n'.encode()
    atomic(folder / 'callas-update-askpass', helper, 0o755)
    icon = Path(prefix) / 'share/icons/hicolor/scalable/apps/callas-update.svg'
    atomic(icon, ICON.encode())
    entry = desktop(gui, icon)
    atomic(Path(prefix) / 'share/applications' / ID, entry)
    return entry, gui

def configure_user(home, entry, gui, documents=None):
    home = Path(home)
    # Same desktop ID shadows the system entry, never a second menu application.
    atomic(home / '.local/share/applications' / ID, entry)
    docs = Path(documents) if documents else home / 'Documentos'
    target = docs / 'Callas OS'
    if target.is_symlink(): raise ValueError('Pasta Callas OS simbólica')
    atomic(target / 'Atualizador do sistema.desktop', entry, 0o755)
    # The historical user-facing shell file now opens the same GUI.
    atomic(target / 'atualizador-do-sistema.sh', f'#!/bin/sh\nexec /usr/bin/python3 "{gui}" "$@"\n'.encode(), 0o755)

def ensure_dependencies():
    if subprocess.run(['/usr/bin/python3', '-c', 'import PySide6'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['/usr/local/libexec/callas-native', '--install', 'pyside6'], check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install-system', metavar='USER')
    parser.add_argument('--user', action='store_true')
    parser.add_argument('--configure-user', action='store_true')
    parser.add_argument('--gui', type=Path)
    args = parser.parse_args()
    source = args.gui or Path(__file__).with_name('callas-update-gui.py')
    if args.install_system:
        if os.geteuid() != 0: raise SystemExit('Requer autorização administrativa.')
        account = pwd.getpwnam(args.install_system)
        if account.pw_uid == 0: raise ValueError('Usuário normal necessário')
        ensure_dependencies()
        entry, gui = deploy(source, Path('/usr/local'))
        installed = Path('/usr/local/libexec/callas-update-gui-install')
        atomic(installed, Path(__file__).read_bytes(), 0o755)
        subprocess.run(['/usr/sbin/runuser', '-u', account.pw_name, '--', '/usr/bin/env',
            'HOME=' + account.pw_dir, '/usr/bin/python3', str(installed), '--configure-user'], check=True)
    elif args.user or args.configure_user:
        if os.geteuid() == 0: raise ValueError('Execute no perfil do usuário normal')
        if args.user:
            entry, gui = deploy(source, Path.home() / '.local')
        else:
            gui = Path('/usr/local/lib/callas-update/callas-update-gui.py')
            entry = Path('/usr/local/share/applications', ID).read_bytes()
        result = subprocess.run(['/usr/bin/xdg-user-dir', 'DOCUMENTS'], capture_output=True, text=True)
        documents = result.stdout.strip() if result.returncode == 0 else ''
        if not documents.startswith('/') or Path(documents) == Path.home(): documents = str(Path.home() / 'Documentos')
        configure_user(Path.home(), entry, gui, documents)
        if shutil.which('kbuildsycoca6'):
            subprocess.run(['kbuildsycoca6', '--noincremental'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else: parser.error('Use --user ou --install-system USER')

if __name__ == '__main__': main()
