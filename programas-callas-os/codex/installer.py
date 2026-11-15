"""Per-user installer. Never modifies Codex authentication or conversation data."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent


def write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink(): raise ValueError('Destino simbólico recusado: '+str(path))
    fd, temp = tempfile.mkstemp(prefix='.callas-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream: stream.write(content)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def desktop_quote(text):
    for char in ('\\', '"', '`', '$'):
        text = text.replace(char, '\\'+char)
    return '"'+text+'"'


def prepare_system_dependencies():
    """Install only missing apps via Callas OS's guarded transaction helper."""
    missing = []
    qt = subprocess.run(['/usr/bin/python3', '-c', 'import PySide6.QtWidgets, PySide6.QtMultimedia'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if qt.returncode: missing.append('pyside6')
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
    has_codex = (shutil.which('codex') or (Path.home()/'.local/bin/codex').is_file()
                 or (data/'callas-chat/runtime/node_modules/.bin/codex').is_file())
    if not has_codex:
        for command, package in (('node', 'nodejs'), ('npm', 'npm')):
            if not shutil.which(command): missing.append(package)
    if not missing: return
    guard = Path('/usr/local/libexec/callas-native')
    if not guard.is_file() or guard.stat().st_uid != 0 or guard.stat().st_mode & 0o022:
        raise ValueError('Atualize a Central Callas OS para preparar as dependências com proteção de kernel e NVIDIA.')
    print('Preparando dependências. Autorize na janela de senha do sistema…', flush=True)
    command = ['/usr/bin/sudo']
    if os.environ.get('SUDO_ASKPASS'): command.append('-A')
    subprocess.run([*command, '--', str(guard), '--install', *missing], check=True)


def install(skip_dependencies=False):
    if os.geteuid() == 0:
        raise ValueError('Execute como seu usuário normal, sem sudo. O instalador pede sudo apenas se faltar um pacote.')
    home = Path.home()
    data = Path(os.environ.get('XDG_DATA_HOME', str(home/'.local/share')))
    base = data/'callas-chat'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if base.is_symlink(): raise ValueError('A pasta do aplicativo não pode ser um link simbólico.')
    interpreter = Path(sys.executable)
    if not skip_dependencies:
        prepare_system_dependencies()
        venv = base/'venv'
        if not (venv/'bin/python').exists():
            subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(venv)], check=True)
        interpreter = venv/'bin/python'
        subprocess.run([str(interpreter), '-c', 'import PySide6.QtWidgets, PySide6.QtMultimedia'], check=True)
        check = subprocess.run([str(interpreter), '-c', "import faster_whisper, scipy; from importlib.metadata import version; assert version('faster-whisper') == '1.2.1' and version('av') == '16.1.0' and version('scipy') == '1.17.0'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode:
            print('Preparando reconhecimento de voz local…', flush=True)
            subprocess.run([str(interpreter), '-m', 'pip', 'install', '--disable-pip-version-check', 'faster-whisper==1.2.1', 'av==16.1.0', 'scipy==1.17.0'], check=True)
        codex = shutil.which('codex') or (str(home/'.local/bin/codex') if (home/'.local/bin/codex').is_file() else '')
        if not codex and not (base/'runtime/node_modules/.bin/codex').exists():
            print('Instalando Codex no perfil do usuário…', flush=True)
            subprocess.run(['npm', 'install', '--prefix', str(base/'runtime'), '@openai/codex@0.169.0'], check=True)
        subprocess.run([str(interpreter), str(SOURCE/'setup_voice.py'), str(base)], check=True)
    app = base/'app'
    previous = base/'app.previous'
    if app.is_symlink() or previous.is_symlink(): raise ValueError('Pasta de instalação simbólica recusada.')
    with tempfile.TemporaryDirectory(prefix='.app-', dir=base) as stage:
        staging = Path(stage)/'app'
        staging.mkdir()
        for name in ('callas_chat', 'assets'):
            shutil.copytree(SOURCE/name, staging/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(SOURCE/'LEIA-ME.txt', staging/'LEIA-ME.txt')
        if previous.exists(): shutil.rmtree(previous)
        if app.exists(): app.rename(previous)
        try: staging.rename(app)
        except BaseException:
            if previous.exists(): previous.rename(app)
            raise
    executable = home/'.local/bin/callas-chat'
    launcher = '#!/usr/bin/env bash\nset -e\nexport PYTHONPATH='+shlex.quote(str(app))+'\nexec '+shlex.quote(str(interpreter))+' -m callas_chat "$@"\n'
    write(executable, launcher, 0o755)
    desktop = data/'applications/io.github.callasos.CallasChat.desktop'
    askpass = home/'.local/bin/codex-askpass'
    write(askpass, '#!/bin/sh\nexport PYTHONPATH='+shlex.quote(str(app))+'\nexec '+shlex.quote(str(interpreter))+' -m callas_chat --askpass \"$@\"\n', 0o755)
    icon = data/'icons/hicolor/scalable/apps/codex.svg'
    icon.parent.mkdir(parents=True, exist_ok=True)
    if icon.is_symlink(): raise ValueError('Ícone de destino simbólico recusado.')
    shutil.copyfile(app/'assets/codex.svg', icon)
    write(desktop, '[Desktop Entry]\nType=Application\nVersion=1.0\nName=Codex\nName[pt_BR]=Codex\n'
          'Comment=Converse com o Codex, use fotos e dite em português\nExec='+desktop_quote(str(executable))+
          '\nIcon='+str(icon)+'\nTerminal=false\nCategories=Utility;\n'
          'Keywords=IA;ChatGPT;conversa;microfone;\nStartupNotify=true\nStartupWMClass=callas-chat\n')
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(desktop.parent)], check=False)
    for command in ('kbuildsycoca6',):
        if shutil.which(command) and not skip_dependencies:
            subprocess.run([command, '--noincremental'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print('\nCodex instalado! Procure “Codex” no menu do KDE.')
    print('Para abrir pelo terminal:', executable)
    print('Seu login e suas conversas do Codex foram preservados.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Instalar Codex neste usuário')
    parser.add_argument('--sem-dependencias', action='store_true', help='Reinstalar somente os arquivos do app; para testes ou dependências já preparadas')
    args = parser.parse_args()
    try: install(args.sem_dependencias)
    except Exception as exc:
        print('Instalação interrompida: '+str(exc), file=sys.stderr)
        raise SystemExit(1)
