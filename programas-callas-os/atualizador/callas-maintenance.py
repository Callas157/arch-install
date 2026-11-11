#!/usr/bin/python3
"""Conservative cleanup and read-only VM inventory. Never deletes VM images/ISOs."""
import contextlib
import fcntl
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PINNED = ('nvidia-utils', 'nvidia-open-dkms', 'nvidia-open', 'nvidia-open-lts',
          'lib32-nvidia-utils', 'nvidia-settings', 'libxnvctrl', 'opencl-nvidia', 'lib32-opencl-nvidia')
PROTECTED = set(PINNED) | {'base', 'base-devel', 'linux', 'linux-lts', 'linux-headers', 'linux-lts-headers',
    'linux-firmware', 'systemd', 'pacman', 'sudo', 'python', 'networkmanager', 'sddm', 'plasma-desktop',
    'konsole', 'dolphin', 'steam', 'discord', 'spotify', 'qbittorrent', 'solaar', 'gnome-boxes',
    'brave-bin', 'paru', 'paru-bin', 'xone-dkms', 'xone-dongle-firmware',
    'gpu-screen-recorder', 'gpu-screen-recorder-gtk', 'nvibrant-bin'}
STORAGE = None
BUILD_ROOT = Path('/var/lib/callas-os/aur-builds')
ROOT_UID = 0

class Tee:
    def __init__(self, console, buffer): self.console, self.buffer = console, buffer
    def write(self, text): self.console.write(text); return self.buffer.write(text)
    def flush(self): self.console.flush()
    def isatty(self): return self.console.isatty()

def storage():
    global STORAGE
    if STORAGE is None:
        path = Path(__file__).with_name('callas-storage')
        if not path.exists(): path = path.with_suffix('.py')
        loader = SourceFileLoader('callas_storage', str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        STORAGE = importlib.util.module_from_spec(spec); loader.exec_module(STORAGE)
    return STORAGE

def run(args, empty_ok=False):
    print('+ ' + ' '.join(args), flush=True)
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if result.stdout: print(result.stdout, end='')
    if result.stderr: print(result.stderr, file=sys.stderr, end='')
    if result.returncode and not (empty_ok and result.returncode == 1 and not result.stdout and not result.stderr):
        raise subprocess.CalledProcessError(result.returncode, args)
    return result.stdout

def orphans():
    result = subprocess.run(['/usr/bin/pacman', '-Qdtq'], stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if result.returncode and not (result.returncode == 1 and not result.stdout and not result.stderr):
        raise RuntimeError(result.stderr or 'Não consegui consultar os pacotes órfãos')
    names = result.stdout.split()
    if any(not re.fullmatch(r'[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\-]*', name) for name in names):
        raise ValueError('Nome de pacote inválido')
    return sorted(name for name in names if name not in PROTECTED and not name.startswith(('linux', 'nvidia', 'lib32-nvidia')))

def manage_orphans():
    names = orphans()
    if not names:
        print('Nenhum candidato a remoção automática/manual foi encontrado. Pacotes essenciais e aplicativos padrão são preservados.')
        return
    print('Candidatos a órfãos (ainda podem ser úteis para você):')
    run(['/usr/bin/pacman', '-Qi', *names])
    if not sys.stdin.isatty():
        print('Sem terminal interativo: somente relatório; nenhum pacote removido.')
        return
    answer = input('Remover somente os pacotes acima? [s/N]: ').strip().lower()
    if answer not in ('s', 'sim'):
        print('Nenhum pacote removido.'); return
    with open('/run/put-update.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if names != orphans():
            print('A lista mudou. Execute novamente para revisar; nenhum pacote removido.'); return
        # No recursive dependency removal and no force flags.
        run(['/usr/bin/pacman', '-R', '--noconfirm', *names])

def vm_report(user):
    account = pwd.getpwnam(user)
    home = Path(account.pw_dir)
    directories = [home / '.local/share/gnome-boxes/images', home / '.cache/gnome-boxes',
        home / '.var/app/org.gnome.Boxes/data/gnome-boxes/images',
        home / '.var/app/org.gnome.Boxes/cache/gnome-boxes', home / '.local/share/libvirt/images',
        Path('/var/lib/libvirt/images')]
    try:
        downloads = storage().as_user(user, ['/usr/bin/xdg-user-dir', 'DOWNLOAD'], capture_output=True, text=True).stdout.strip()
        if downloads.startswith(str(home) + '/'):
            directories.append(Path(downloads))
    except (FileNotFoundError, subprocess.SubprocessError):
        directories += [home / 'Downloads', home / 'Baixados']
    referenced = set()
    if Path('/usr/bin/virsh').exists():
        try:
            result = storage().as_user(user, ['/usr/bin/virsh', '-c', 'qemu:///session', 'list', '--all', '--uuid'],
                                       capture_output=True, text=True, timeout=20)
            for identifier in result.stdout.split():
                if not re.fullmatch(r'[a-fA-F0-9-]{36}', identifier): continue
                result = storage().as_user(user, ['/usr/bin/virsh', '-c', 'qemu:///session', 'dumpxml', identifier],
                                           capture_output=True, text=True, timeout=20)
                tree = ET.fromstring(result.stdout)
                referenced.update(node.attrib['file'] for node in tree.findall('.//disk/source') if 'file' in node.attrib)
        except (subprocess.SubprocessError, ET.ParseError) as error:
            print('Consulta do libvirt indisponível/incompleta: ' + str(error))
    print('Inventário de VMs: não apaga nem altera máquinas, discos, snapshots ou ISOs.')
    print('Sem associação visível NÃO significa arquivo abandonado (Flatpak, snapshots e outros gerenciadores podem utilizá-lo).')
    for directory in directories:
        if not directory.is_dir() or directory.is_symlink(): continue
        print('Pasta: ' + str(directory))
        for parent, dirs, files in os.walk(directory, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(parent) / name).is_symlink()]
            for name in files:
                path = Path(parent) / name
                if path.is_symlink() or path.suffix.lower() not in ('.qcow2', '.qcow', '.img', '.iso'): continue
                info = path.stat()
                used = info.st_blocks * 512 / 1024**2
                state = 'associado a VM consultada' if str(path) in referenced else 'associação não confirmada'
                print(f'{used:.1f} MiB usados | {state} | {path}')

def clean(user):
    with open('/run/put-update.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with storage().Backups(user) as backups:
            backups.migrate(); total = backups.rotate()
            print(f'Backups após rotação: {total / 1024**2:.2f} MiB; limite combinado de {backups.limit} bytes.')
        database = Path(run(['/usr/bin/pacman-conf', 'DBPath']).strip())
        with storage().package_database_lock(database):
            run(['/usr/bin/paccache', '-r', '-k', '3', '--ignore', ','.join(PINNED)])
        run(['/usr/bin/systemd-tmpfiles', '--clean', '--prefix=/tmp', '--prefix=/var/tmp'])
        prune_builds()
        run(['/usr/local/libexec/callas-logs', '--prune-root'])
        storage().as_user(user, ['/usr/local/libexec/callas-logs', '--prune'])
        print('Limpeza segura concluída. Órfãos, VMs, ISOs, navegador e caches de shaders não foram removidos.')

def prune_builds():
    if not BUILD_ROOT.is_dir() or BUILD_ROOT.is_symlink(): return
    if not shutil.rmtree.avoids_symlink_attacks: return
    fd = storage().open_directory(BUILD_ROOT)
    try:
        if os.fstat(fd).st_uid != ROOT_UID: raise ValueError('Pasta de compilações com dono inesperado')
        for name in os.listdir(fd):
            if not re.fullmatch(r'transaction-[a-z0-9_]{8}', name): continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode) and info.st_uid == ROOT_UID and info.st_mtime < time.time() - 7 * 86400:
                # Build units have a 2-hour maximum lifetime; normal/failed builds
                # already remove their stage. This covers old interrupted stages.
                shutil.rmtree(name, dir_fd=fd)
                print('Restos antigos de compilação removidos: ' + name)
    finally: os.close(fd)

def main():
    if os.geteuid() != 0 or len(sys.argv) != 3:
        raise SystemExit('Use a opção 1 — Limpeza e manutenção no Atualizador do sistema.')
    action, user = sys.argv[1:]
    if action not in ('--clean', '--report', '--orphans'): raise ValueError('Ação inválida')
    if pwd.getpwnam(user).pw_uid == 0: raise ValueError('Informe usuário normal')
    os.umask(0o077)
    output = io.StringIO(); code = 0
    try:
        print('Executando manutenção; aguarde...' if action == '--clean' else 'Preparando relatório...', flush=True)
        interactive = action == '--orphans'
        with contextlib.redirect_stdout(Tee(sys.stdout, output) if interactive else output), contextlib.redirect_stderr(output):
            if action == '--clean': clean(user)
            elif action == '--orphans': manage_orphans()
            else:
                with storage().Backups(user) as backups:
                    print('Backups: ' + str(backups.path))
                    print(f'Limite combinado: {backups.limit} bytes; até {backups.keep} cópias por categoria.')
                    print('Configuração administrativa: /etc/callas-os/maintenance.ini')
                    for _, category, name, size in backups.entries(): print(f'{category}/{name}: {size / 1024**2:.2f} MiB')
                print('Logs: ' + str(storage().documents_for(user) / 'Callas OS' / 'Callas OS Logs'))
                usage = shutil.disk_usage('/')
                print(f'Partição do sistema: {(usage.total-usage.free)/1024**3:.1f} GiB usados; {usage.free/1024**3:.1f} GiB livres.')
                paths = ['/var/cache/pacman/pkg', '/var/log/callas-os', str(storage().documents_for(user) / 'Callas OS' / 'Callas OS Logs')]
                present = [path for path in paths if Path(path).exists()]
                if present: run(['/usr/bin/du', '-sh', *present])
                vm_report(user)
    except Exception as error:
        output.write('Manutenção interrompida: ' + str(error) + '\n'); code = 1
    data = output.getvalue().encode()
    if action != '--orphans': print(output.getvalue(), end='')
    subprocess.run(['/usr/local/libexec/callas-logs', '--record', 'Manutencao'], input=data, check=True)
    subprocess.run(['/usr/local/libexec/callas-logs', '--export', user], check=True)
    return code

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as error:
        print('Falha na manutenção: ' + str(error), file=sys.stderr); sys.exit(1)
