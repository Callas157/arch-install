#!/usr/bin/python3
"""Bounded logs, unprivileged Documents writes, idempotent administrative export."""
import datetime
import hashlib
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time

CATEGORIES = ('Callas OS Update', 'Sistema e Pacman', 'Kernel Linux', 'Driver NVIDIA',
              'Aplicativos', 'AUR', 'Seguranca e Firewall', 'Instalacao', 'Manutencao', 'Janelas', 'Jogos')
MAX_FILE = 2 * 1024**2
MAX_TOTAL = 128 * 1024**2
MAX_AGE = 30 * 86400
MAX_FILES = 60
ROOT = Path('/var/log/callas-os')

def documents():
    try: result = subprocess.run(['/usr/bin/xdg-user-dir', 'DOCUMENTS'], capture_output=True, text=True)
    except FileNotFoundError:
        return Path.home() / ('Documents' if (Path.home() / 'Documents').is_dir() else 'Documentos')
    value = result.stdout.strip()
    if result.returncode or not value.startswith('/') or Path(value) == Path.home():
        return Path.home() / 'Documentos'
    return Path(value)

def prepare():
    if os.geteuid() == 0: raise ValueError('A pasta pessoal deve ser preparada pelo próprio usuário')
    docs = documents(); docs.mkdir(parents=True, exist_ok=True)
    project = docs / 'Callas OS'; project.mkdir(mode=0o700, exist_ok=True)
    if project.is_symlink(): raise ValueError('Pasta Callas OS simbólica; conteúdo preservado')
    base = project / 'Callas OS Logs'
    if base.is_symlink(): raise ValueError('Pasta de logs simbólica; conteúdo preservado')
    for name in ('Callas OS Logs', 'Logs do Callas OS', 'Logs de Atualizações'):
        old = docs / name
        if old.is_dir() and not old.is_symlink():
            if not base.exists(): old.rename(base)
            else:
                dest = base / ('Legado-' + name)
                while dest.exists(): dest = base / (dest.name + '-' + str(time.time_ns()))
                shutil.move(str(old), str(dest))
    base.mkdir(mode=0o700, exist_ok=True)
    for category in CATEGORIES:
        (base / category).mkdir(mode=0o700, exist_ok=True)
    return base

def tail(data):
    return data if len(data) <= MAX_FILE else b'[Inicio do log omitido por limite de tamanho]\n' + data[-MAX_FILE + 64:]

def read_tail(stream):
    data = b''
    for block in iter(lambda: stream.read(64 * 1024), b''):
        data = (data + block)[-MAX_FILE:]
    return data

def prune(base):
    files = []
    if base.is_symlink(): return
    for directory, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
        group = []
        for name in names:
            path = Path(directory) / name
            if path.suffix != '.log' or path.is_symlink() or not path.is_file(): continue
            info = path.stat()
            if info.st_mtime < time.time() - MAX_AGE:
                path.unlink(); continue
            group.append((info.st_mtime_ns, path, info.st_size))
        group.sort()
        for _, path, _ in group[:-MAX_FILES]: path.unlink()
        files += group[-MAX_FILES:]
    total = sum(size for _, _, size in files)
    for _, path, size in sorted(files):
        if total <= MAX_TOTAL: break
        path.unlink(); total -= size

def identified(data):
    helper = Path('/usr/local/libexec/callas-version')
    if not helper.is_file(): return tail(data)
    result = subprocess.run([str(helper), '--context'], capture_output=True, text=True, check=True)
    if data.startswith(b'Callas OS | '): return tail(data)
    header = ('Callas OS | ' + result.stdout.strip() + '\n').encode()
    header = header[:MAX_FILE]
    remaining = MAX_FILE - len(header)
    return header + (tail(data)[-remaining:] if remaining else b'')

def create_log(base):
    # The name records the local completion time. A readable sequence prevents
    # overwrites when two diagnostics finish in the same second.
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%Hh%Mm%Ss')
    for number in range(1, 10001):
        suffix = '' if number == 1 else '__parte-' + str(number).zfill(2)
        path = base / (stamp + suffix + '.log')
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            return fd, path
        except FileExistsError:
            continue
    raise RuntimeError('Muitos logs no mesmo segundo; nenhum arquivo foi substituído')


def completed(data):
    timestamp = datetime.datetime.now().astimezone().strftime('%d/%m/%Y às %H:%M:%S %z')
    return identified(('Encerrado em: ' + timestamp + '\n').encode() + data)

def write_log(category, data, origin=None):
    if os.geteuid() == 0 or category not in CATEGORIES:
        raise ValueError('Categoria ou usuário inválido')
    base = prepare()
    if origin is not None:
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', origin): raise ValueError('Origem inválida')
        filename = origin if origin.endswith('.log') else origin + '.log'
        path = base / category / filename
        try: fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            return path  # This exact root log was already exported.
    else:
        fd, path = create_log(base / category)
    # Imported diagnostics retain their original context, including old logs
    # that predate project versioning. Do not label old events as today's OS.
    with os.fdopen(fd, 'wb') as stream: stream.write(tail(data) if origin is not None else completed(data))
    prune(base)
    return path

def root_log(category, data):
    if category not in CATEGORIES: raise ValueError('Categoria inválida')
    if os.geteuid() != 0: return write_log(category, data)
    base = ROOT / category
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, path = create_log(base)
    with os.fdopen(fd, 'wb') as stream: stream.write(completed(data))
    prune(ROOT)

def user_command(user, *args, **kwargs):
    account = pwd.getpwnam(user)
    if account.pw_uid == 0: raise ValueError('Informe usuário normal')
    env = ['PATH=/usr/bin:/bin', 'HOME=' + account.pw_dir, 'USER=' + user,
           'LOGNAME=' + user, 'LANG=C.UTF-8']
    return subprocess.run(['/usr/bin/runuser', '-u', user, '--', '/usr/bin/env', '-i',
                           *env, '/usr/local/libexec/callas-logs', *args], check=True, **kwargs)

def export(user):
    user_command(user, '--prepare', stdout=subprocess.DEVNULL)
    for category in CATEGORIES:
        base = ROOT / category
        if not base.is_dir() or base.is_symlink(): continue
        for path in sorted(base.glob('*.log')):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream: data = read_tail(stream)
            user_command(user, '--write', category, '--origin', path.name, input=data)
    for path, category in ((Path('/var/log/pacman.log'), 'Sistema e Pacman'),
                           (Path('/var/log/callas-instalacao-avisos.log'), 'Instalacao')):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                stream.seek(0, 2); stream.seek(max(0, stream.tell() - MAX_FILE)); data = stream.read()
            stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d_%Hh%Mm%Ss')
            origin = path.stem + '-' + stamp + '-' + hashlib.sha256(data).hexdigest()[:8] + '.log'
            user_command(user, '--write', category, '--origin', origin, input=data)

def main():
    os.umask(0o077)
    args = sys.argv[1:]
    if args == ['--prepare']: print(prepare())
    elif args == ['--prune'] and os.geteuid() != 0: prune(prepare())
    elif args == ['--prune-root'] and os.geteuid() == 0: prune(ROOT)
    elif len(args) in (2, 4) and args[0] == '--write':
        if len(args) == 4 and args[2] != '--origin': raise ValueError('Argumento inválido')
        write_log(args[1], read_tail(sys.stdin.buffer), args[3] if len(args) == 4 else None)
    elif len(args) == 2 and args[0] == '--record': root_log(args[1], read_tail(sys.stdin.buffer))
    elif len(args) == 2 and args[0] == '--export' and os.geteuid() == 0: export(args[1])
    else: raise SystemExit('Uso interno do Callas OS')

if __name__ == '__main__': main()
