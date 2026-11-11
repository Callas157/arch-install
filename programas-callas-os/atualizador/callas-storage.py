#!/usr/bin/python3
"""Bounded administrative backups in Documents, using directory FDs/no symlinks.

Archives remain root:root 0600: legacy recovery archives can contain /etc/shadow.
Only the three updater-owned legacy pools are migrated; VM images are never touched.
"""
import datetime
import configparser
import contextlib
import gzip
import io
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

ROOT_UID = 0
LIMIT = 1_000_000_000
KEEP = 3
CATEGORIES = ('Sistema', 'Callas OS Update', 'Seguranca')
LEGACY = {
    Path('/var/lib/put-update/recuperacao'): 'Sistema',
    Path('/var/lib/callas-os/config-backups'): 'Callas OS Update',
    Path('/var/lib/callas-os/security-backups'): 'Seguranca',
}
SNAPSHOT = re.compile(r'\d{8}-\d{6}(?:\.[A-Za-z0-9]+)?\Z')
ARCHIVE = re.compile(r'\d{8}-\d{6}-[a-f0-9]{12}\.tar\.gz\Z')
POLICY = Path('/etc/callas-os/maintenance.ini')

def policy():
    config = configparser.ConfigParser()
    config.read(POLICY)
    limit = config.getint('Backups', 'limit_bytes', fallback=LIMIT)
    keep = config.getint('Backups', 'copies_per_type', fallback=KEEP)
    if not 1 <= limit <= 100 * 1024**3 or not 1 <= keep <= 20:
        raise ValueError('Limite de backup inválido; nenhum arquivo foi apagado')
    return limit, keep

def as_user(user, args, **kwargs):
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError('Informe um usuário normal')
    env = ['PATH=/usr/bin:/bin', 'HOME=' + account.pw_dir, 'USER=' + user,
           'LOGNAME=' + user, 'LANG=C.UTF-8']
    return subprocess.run(['/usr/bin/runuser', '-u', user, '--', '/usr/bin/env', '-i',
                           *env, *args], check=True, **kwargs)

def documents_for(user):
    account = pwd.getpwnam(user)
    try:
        result = as_user(user, ['/usr/bin/xdg-user-dir', 'DOCUMENTS'], capture_output=True, text=True)
        value = result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        value = account.pw_dir + ('/Documents' if Path(account.pw_dir, 'Documents').is_dir() else '/Documentos')
    if not value.startswith('/') or value == account.pw_dir:
        value = account.pw_dir + '/Documentos'
    # Creation is deliberately unprivileged, even if XDG points elsewhere.
    as_user(user, ['/usr/bin/python3', '-c',
                  'from pathlib import Path; import sys; Path(sys.argv[1]).mkdir(parents=True,exist_ok=True,mode=0o700)', value])
    return Path(value)

def open_directory(path):
    """Never follow a user-swapped symlink at any component of a privileged write."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Caminho de backup inválido')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise

@contextlib.contextmanager
def package_database_lock(directory):
    lock = Path(directory) / 'db.lck'
    try: fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise RuntimeError('O Pacman está ocupado; o backup e a atualização devem aguardar')
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        try:
            before, current = os.fstat(fd), lock.lstat()
            if (before.st_dev, before.st_ino) == (current.st_dev, current.st_ino): lock.unlink()
        except FileNotFoundError: pass
        os.close(fd)

class LimitedWriter:
    def __init__(self, stream, limit): self.stream, self.limit = stream, limit
    def write(self, data):
        if self.stream.tell() + len(data) > self.limit:
            raise OverflowError('Uma única cópia excede o limite de backup')
        return self.stream.write(data)
    def __getattr__(self, attr): return getattr(self.stream, attr)

class Backups:
    def __init__(self, user, documents=None, limit=None, keep=None):
        configured_limit, configured_keep = policy()
        limit = configured_limit if limit is None else limit
        keep = configured_keep if keep is None else keep
        self.user, self.limit, self.keep = user, limit, keep
        docs = documents or documents_for(user)
        account = pwd.getpwnam(user)
        parent = open_directory(docs)
        try:
            if os.fstat(parent).st_uid != account.pw_uid:
                raise ValueError('A pasta Documentos não pertence ao usuário informado')
            created = False
            try:
                os.mkdir('Callas OS Backup', 0o755, dir_fd=parent); created = True
            except FileExistsError: pass
            self.fd = os.open('Callas OS Backup', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            if created: os.fchmod(self.fd, 0o755)
        finally:
            os.close(parent)
        self.path = Path(docs) / 'Callas OS Backup'
        info = os.fstat(self.fd)
        if info.st_uid != ROOT_UID or stat.S_IMODE(info.st_mode) & 0o022:
            self.close()
            raise ValueError('Pasta de backup com dono/permissões inesperados; nenhum arquivo foi apagado')
        self.directories = {}
        try:
            for category in CATEGORIES:
                created = False
                try: os.mkdir(category, 0o755, dir_fd=self.fd); created = True
                except FileExistsError: pass
                fd = os.open(category, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
                if created: os.fchmod(fd, 0o755)
                info = os.fstat(fd)
                if info.st_uid != ROOT_UID or stat.S_IMODE(info.st_mode) & 0o022:
                    os.close(fd)
                    raise ValueError('Categoria de backup insegura')
                self.directories[category] = fd
        except BaseException:
            self.close(); raise

    def close(self):
        for fd in getattr(self, 'directories', {}).values(): os.close(fd)
        self.directories = {}
        if getattr(self, 'fd', None) is not None:
            os.close(self.fd); self.fd = None
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def entries(self):
        entries = []
        for category, fd in self.directories.items():
            for name in os.listdir(fd):
                if not ARCHIVE.fullmatch(name): continue
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISREG(info.st_mode) and info.st_uid == ROOT_UID:
                    entries.append((info.st_mtime_ns, category, name, info.st_size))
        return sorted(entries)

    def rotate(self):
        for fd in self.directories.values():
            for name in os.listdir(fd):
                if not re.fullmatch(r'\.partial-[a-f0-9]{32}', name): continue
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISREG(info.st_mode) and info.st_uid == ROOT_UID and info.st_mtime < time.time() - 86400:
                    os.unlink(name, dir_fd=fd)
        entries = self.entries()
        remove = set()
        for category in CATEGORIES:
            group = [entry for entry in entries if entry[1] == category]
            remove.update((entry[1], entry[2]) for entry in group[:-self.keep])
        total = sum(entry[3] for entry in entries if (entry[1], entry[2]) not in remove)
        for entry in entries:
            key = entry[1], entry[2]
            if total <= self.limit: break
            if key not in remove:
                remove.add(key); total -= entry[3]
        for _, category, name, _ in entries:
            if (category, name) not in remove: continue
            os.unlink(name, dir_fd=self.directories[category])
            print('Backup antigo removido: ' + category + '/' + name)
        return sum(entry[3] for entry in self.entries())

    def create(self, category, sources, extra=None, mtime=None):
        if category not in self.directories: raise ValueError('Categoria inválida')
        self.rotate()
        now = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        name = now + '-' + uuid.uuid4().hex[:12] + '.tar.gz'
        stage = '.partial-' + uuid.uuid4().hex
        fd = self.directories[category]
        out_fd = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            with os.fdopen(out_fd, 'wb') as stream:
                limited = LimitedWriter(stream, self.limit)
                with tarfile.open(fileobj=limited, mode='w:gz', dereference=False) as archive:
                    for source in sources:
                        source = Path(source)
                        if source.exists() or source.is_symlink():
                            archive.add(source, arcname=str(source).lstrip('/'), recursive=True,
                                        filter=lambda entry: entry if (entry.isfile() or entry.isdir() or entry.issym()) else None)
                    for label, data in (extra or {}).items():
                        entry = tarfile.TarInfo(label); entry.size = len(data); entry.mode = 0o600
                        archive.addfile(entry, io.BytesIO(data))
                stream.flush(); os.fsync(stream.fileno())
            os.rename(stage, name, src_dir_fd=fd, dst_dir_fd=fd)
            if mtime is not None: os.utime(name, (mtime, mtime), dir_fd=fd, follow_symlinks=False)
            self.rotate()
            print('Backup: ' + str(self.path / category / name))
            return name
        except OverflowError:
            print('Aviso: cópia maior que o limite; não foi armazenada. As cópias anteriores foram preservadas.', file=sys.stderr)
            return None
        finally:
            try: os.unlink(stage, dir_fd=fd)
            except FileNotFoundError: pass

    def migrate(self):
        for base, category in LEGACY.items():
            if not base.is_dir() or base.is_symlink(): continue
            for item in sorted(base.iterdir()):
                if not SNAPSHOT.fullmatch(item.name) or item.is_symlink() or not item.is_dir(): continue
                # Import first; old pools are removed only after a complete archive
                # was written. Oversized/unreadable legacy copies remain with warning.
                result = self.create(category, [item], mtime=item.stat().st_mtime)
                if result:
                    shutil.rmtree(item)
                    print('Cópia antiga migrada: ' + str(item))
            try: base.rmdir()
            except OSError: pass
        self.rotate()

def snapshot(backups, kind, user):
    home = Path(pwd.getpwnam(user).pw_dir)
    if kind == '--system':
        database = Path(subprocess.check_output(['/usr/bin/pacman-conf', 'DBPath'], text=True).strip())
        with package_database_lock(database):
            extra = {}
            for filename, flag in (('pacotes.txt', '-Q'), ('pacotes-explicitos.txt', '-Qqe')):
                extra[filename] = subprocess.check_output(['/usr/bin/pacman', flag])
            return backups.create('Sistema', ['/etc', database / 'local', '/boot/grub/grub.cfg'], extra)
    if kind == '--security':
        return backups.create('Seguranca', ['/etc/pacman.conf', '/etc/sudoers.d', '/etc/sysctl.d/60-callas-security.conf'])
    if kind == '--config':
        sources = ['/etc/default/grub', '/boot/grub/grub.cfg', '/etc/xdg/kicker-extra-favoritesrc',
                   '/etc/xdg/autostart/callas-limpar-atalhos-desktop.desktop',
                   home / '.config/powerdevilrc', home / '.config/ksmserverrc',
                   home / '.config/BraveSoftware/Brave-Browser/Default/Preferences']
        sources += list(Path('/usr/local/libexec').glob('callas-*'))
        return backups.create('Callas OS Update', sources)

def main():
    if os.geteuid() != 0 or len(sys.argv) != 3:
        raise SystemExit('Uso interno: callas-storage AÇÃO USUARIO')
    action, user = sys.argv[1:]
    if action not in ('--system', '--security', '--config', '--migrate', '--rotate', '--report'):
        raise ValueError('Ação inválida')
    os.umask(0o077)
    with Backups(user) as backups:
        if action == '--migrate': backups.migrate()
        elif action == '--rotate': backups.rotate()
        elif action == '--report':
            print('Pasta: ' + str(backups.path))
            print(f'Limite combinado: {backups.limit} bytes; até {backups.keep} cópias por categoria. Configuração: {POLICY}')
            for _, category, name, size in backups.entries(): print(f'{category}/{name}: {size / 1024**2:.2f} MiB')
            print(f'Total: {sum(entry[3] for entry in backups.entries()) / 1024**2:.2f} MiB')
        else: snapshot(backups, action, user)

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Falha no armazenamento de backups: ' + str(error), file=sys.stderr)
        sys.exit(1)
