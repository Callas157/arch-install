#!/usr/bin/python3
"""Recover existing Steam libraries before the native client starts."""
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

MAX_VDF = 2 * 1024 * 1024
DATA_FILESYSTEMS = {'btrfs', 'exfat', 'ext2', 'ext3', 'ext4', 'f2fs', 'ntfs', 'ntfs3', 'fuseblk', 'xfs'}
TOKEN = re.compile(r'(?P<ignored>\s+|//[^\r\n]*)|(?P<string>"(?:[^"\\]|\\.)*")|(?P<brace>[{}])')
MANIFEST = re.compile(r'appmanifest_[1-9][0-9]{0,19}\.acf')


@dataclass
class Value:
    data: str | dict
    start: int
    end: int


def vdf_string(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def parse_vdf(text, heading):
    def tokens():
        start = 0
        while start < len(text):
            match = TOKEN.match(text, start)
            if not match:
                raise ValueError('Formato VDF não reconhecido')
            start = match.end()
            if match.lastgroup != 'ignored':
                yield match

    def string(token):
        if token is None or token.lastgroup != 'string':
            raise ValueError('Campo VDF inválido')
        return re.sub(r'\\(["\\])', r'\1', token[0][1:-1])

    def section(opening, depth):
        if depth > 16:
            raise ValueError('VDF com aninhamento inesperado')
        fields = {}
        for key_token in stream:
            if key_token[0] == '}':
                return Value(fields, opening.start(), key_token.end())
            key = string(key_token).lower()
            if key in fields:
                raise ValueError('Campo VDF duplicado')
            token = next(stream, None)
            fields[key] = (section(token, depth + 1) if token is not None and token[0] == '{'
                           else Value(string(token), token.start(), token.end()))
        raise ValueError('Seção VDF incompleta')

    stream = tokens()
    name = string(next(stream, None))
    opening = next(stream, None)
    if name.lower() != heading or opening is None or opening[0] != '{':
        raise ValueError('Cabeçalho VDF inválido')
    value = section(opening, 0)
    if next(stream, None) is not None:
        raise ValueError('Dados VDF adicionais')
    return value


def safe_path(value):
    if not value or not value.startswith('/') or any(ord(char) < 32 for char in value):
        return None
    path = Path(value)
    return path if '..' not in path.parts and path.anchor == '/' else None


def data_relative(path, user):
    """Return the path inside a historical data mount."""
    parts = path.parts
    if len(parts) >= 3 and parts[1] in ('media', 'mnt'):
        return parts[3:]
    if len(parts) >= 5 and parts[1:4] == ('run', 'media', user):
        return parts[5:]
    return None


def find_mounts(user):
    def filesystems(mode):
        result = subprocess.run(
            ['/usr/bin/findmnt', mode, '--json', '--list', '--evaluate', '--nofsroot',
             '-o', 'SOURCE,TARGET,FSTYPE,OPTIONS'],
            check=True, capture_output=True, text=True, timeout=5)
        return json.loads(result.stdout).get('filesystems') or []

    def block_number(source):
        if not source or not source.startswith('/dev/'):
            return None
        try:
            info = os.stat(source)
            return info.st_rdev if stat.S_ISBLK(info.st_mode) else None
        except OSError:
            return None

    configured = {}
    for entry in filesystems('--fstab'):
        path = safe_path(entry.get('target'))
        options = set((entry.get('options') or '').split(','))
        if (path and data_relative(path, user) is not None
                and not {'noauto', 'ro'}.intersection(options)):
            configured.setdefault(path, []).append(block_number(entry.get('source')))
    current = filesystems('--kernel')
    protected = {block_number(entry.get('source')) for entry in current
                 if (path := safe_path(entry.get('target'))) is not None
                 and data_relative(path, user) is None}
    target_counts = Counter(entry.get('target') for entry in current)
    mounted = {}
    for entry in current:
        path = safe_path(entry.get('target'))
        number = block_number(entry.get('source')) if path in configured else None
        options = set((entry.get('options') or '').split(','))
        if (number is not None and number not in protected and configured[path] == [number]
                and target_counts[entry['target']] == 1 and 'rw' in options
                and entry.get('fstype') in DATA_FILESYSTEMS):
            try:
                if path.resolve() == path:
                    mounted[path] = number
            except (OSError, RuntimeError):
                continue
    return mounted


def read_file(path, *, owned):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > MAX_VDF
                or (owned and before.st_uid != os.geteuid())):
            raise ValueError('Arquivo VDF inseguro')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            payload = stream.read(MAX_VDF + 1)
        if len(payload) > MAX_VDF or file_identity(before) != file_identity(os.fstat(fd)):
            raise ValueError('Arquivo VDF mudou durante a leitura')
        return payload, before
    finally:
        os.close(fd)


def file_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def numeric_id(value):
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,19}', value) and int(value) < 2**64:
        return value
    return None


def catalog(document):
    entries = []
    for key, entry in document.data.items():
        if not key.isascii() or not key.isdecimal():
            continue
        fields = entry.data
        if isinstance(fields, dict):
            path = fields.get('path')
            ident = fields.get('contentid')
        else:
            path, ident = entry, None  # Legacy libraryfolders.vdf string entry.
        if path is None or not isinstance(path.data, str):
            raise ValueError('Local de biblioteca Steam inválido')
        entries.append((key, path, numeric_id(ident.data) if ident else None))
    if not any(key == '0' and safe_path(path.data) for key, path, _ in entries):
        raise ValueError('Biblioteca Steam principal ausente')
    return entries


def native_steam(home):
    paths = (home / '.steam/root', home / '.steam/steam', home / '.local/share/Steam')
    for path in paths:
        try:
            root = path.resolve(strict=True)
            apps = root / 'steamapps'
            if (root.stat().st_uid == os.geteuid() and apps.resolve(strict=True) == apps
                    and apps.stat().st_uid == os.geteuid()
                    and (apps / 'libraryfolders.vdf').is_file()):
                return root
        except (OSError, RuntimeError):
            pass
    return None


def library_info(path, device):
    """Identify a readable library on this same mounted filesystem."""
    try:
        apps = path / 'steamapps'
        if (safe_path(str(path)) is None or apps.resolve(strict=True) != apps
                or apps.stat().st_dev != device
                or not os.access(apps, os.R_OK | os.X_OK)):
            return None
        with os.scandir(apps) as entries:
            if not any(MANIFEST.fullmatch(entry.name) and entry.is_file(follow_symlinks=False)
                       and entry.stat(follow_symlinks=False).st_size > 0
                       and os.access(entry.path, os.R_OK)
                       for entry in islice(entries, 8192)):
                return None
        try:
            data, _ = read_file(path / 'libraryfolder.vdf', owned=False)
            fields = parse_vdf(data.decode('utf-8-sig'), 'libraryfolder').data
            ident = fields.get('contentid')
            if ident and (known := numeric_id(ident.data)):
                return known
        except (OSError, ValueError):
            pass
        # Keep both catalog copies consistent when Steam has not yet written a marker.
        digest = hashlib.blake2b(os.fsencode(path), digest_size=8).digest()
        return str((int.from_bytes(digest, 'big') >> 1) or 1)
    except (OSError, RuntimeError):
        return None


def discover_libraries(mounts, entries, user, root):
    relatives = {(), ('SteamLibrary',), ('Steam',)}
    for _, value, _ in entries:
        path = safe_path(value.data)
        if path is not None:
            relative = data_relative(path, user)
            if relative is not None and len(relative) <= 8:
                relatives.add(relative)

    libraries = {}
    for mount in sorted(mounts):
        try:
            device = mount.stat().st_dev
            with os.scandir(mount) as children:
                candidates = {mount / child.name for child in islice(children, 512)
                              if child.is_dir(follow_symlinks=False)}
        except OSError:
            continue
        candidates.update(mount.joinpath(*relative) for relative in relatives)
        for path in sorted(candidates):
            if path != root and (ident := library_info(path, device)):
                libraries[path] = ident
    return libraries


def accessible(path):
    return path is not None and os.access(path / 'steamapps', os.R_OK | os.X_OK)


def revised_vdf(original, document, entries, libraries):
    known_paths = set()
    for _, value, _ in entries:
        if path := safe_path(value.data):
            try:
                known_paths.add(path.resolve())
            except (OSError, RuntimeError):
                known_paths.add(path)
    disk_ids = Counter(libraries.values())
    used_ids = Counter(ident for _, _, ident in entries if ident)
    next_key = max(int(key) for key, _, _ in entries) + 1
    legacy = all(isinstance(document.data[key].data, str) for key, _, _ in entries)
    changes = []
    additions = []
    newline = '\r\n' if '\r\n' in original else '\n'
    for path, ident in sorted(libraries.items()):
        if path in known_paths or disk_ids[ident] > 1 or used_ids[ident] > 1:
            continue
        if used_ids[ident]:
            key, old, _ = next(entry for entry in entries if entry[2] == ident)
            if key != '0' and not accessible(safe_path(old.data)):
                changes.append((old.start, old.end, vdf_string(str(path))))
            continue
        if legacy:
            additions.append(f'\t"{next_key}"\t\t{vdf_string(str(path))}' + newline)
        else:
            fields = (f'\t"{next_key}"', '\t{', '\t\t"path"\t\t' + vdf_string(str(path)),
                      '\t\t"label"\t\t""', f'\t\t"contentid"\t\t"{ident}"',
                      '\t\t"totalsize"\t\t"0"', '\t\t"apps"\t\t{}', '\t}', '')
            additions.append(newline.join(fields))
        next_key += 1
    if additions:
        end = document.end - 1
        prefix = '' if original[end - 1] in '\r\n' else newline
        changes.append((end, end, prefix + ''.join(additions)))
    for start, end, replacement in sorted(changes, reverse=True):
        original = original[:start] + replacement + original[end:]
    return original


def steam_running():
    status = subprocess.run(
        ['/usr/bin/pgrep', '-u', str(os.geteuid()), '--runstates', 'D,I,K,P,R,S,T,t,W',
         '-x', 'steam|steamwebhelper|steamcmd'],
        stdout=subprocess.DEVNULL, check=False, timeout=5).returncode
    return status != 1


@contextmanager
def recovery_lock(steamapps):
    path = steamapps / '.callas-libraryfolders.lock'
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError('Bloqueio da Steam inseguro')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def store_update(path, previous, value, mode):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.callas-steam-', delete=False) as stream:
        staged = Path(stream.name)
        try:
            stream.write(value)
            stream.flush()
            os.fchmod(stream.fileno(), stat.S_IMODE(mode.st_mode) & 0o777)
            os.fsync(stream.fileno())
            current, identity = read_file(path, owned=True)
            if file_identity(identity) == file_identity(mode) and current == previous and not steam_running():
                os.replace(staged, path)
        finally:
            staged.unlink(missing_ok=True)


def recover(home, user):
    root = native_steam(home)
    if root is None or steam_running():
        return
    with recovery_lock(root / 'steamapps'):
        if steam_running():
            return
        mounts = find_mounts(user)
        if not mounts:
            return
        catalogs = []
        for path in (root / 'steamapps/libraryfolders.vdf', root / 'config/libraryfolders.vdf'):
            if path.parent.resolve() != path.parent:
                continue
            try:
                previous, mode = read_file(path, owned=True)
                encoding = 'utf-8-sig' if previous.startswith(b'\xef\xbb\xbf') else 'utf-8'
                text = previous.decode(encoding)
                document = parse_vdf(text, 'libraryfolders')
                catalogs.append((path, previous, mode, encoding, text, document, catalog(document)))
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as error:
                print(f'Recuperação de bibliotecas Steam: {path}: {error}', file=sys.stderr)
        if not catalogs:
            return
        entries = [entry for _, _, _, _, _, _, items in catalogs for entry in items]
        libraries = discover_libraries(mounts, entries, user, root)
        if not libraries or find_mounts(user) != mounts:
            return
        for path, previous, mode, encoding, text, document, items in catalogs:
            revised = revised_vdf(text, document, items, libraries)
            if revised != text:
                catalog(parse_vdf(revised, 'libraryfolders'))
                store_update(path, previous, revised.encode(encoding), mode)


def main():
    if os.geteuid() == 0 or len(sys.argv) != 1:
        raise ValueError('Uso interno na sessão do usuário, sem argumentos')
    from pwd import getpwuid
    account = getpwuid(os.geteuid())
    recover(Path(account.pw_dir), account.pw_name)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Recuperação de bibliotecas Steam: {error}', file=sys.stderr)
