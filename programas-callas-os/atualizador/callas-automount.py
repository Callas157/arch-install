#!/usr/bin/python3
"""Prepare boot mounts for local secondary data partitions."""
from collections import defaultdict
from contextlib import contextmanager, suppress
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile

FSTAB = Path('/etc/fstab')
MARKER = '# Montagem de discos de dados — Callas OS'
END_MARKER = '# Fim da montagem de discos de dados — Callas OS'
MANAGED_OPTIONS = {'nosuid', 'nodev', 'nofail', 'x-systemd.device-timeout=10s',
                   'x-systemd.mount-timeout=15s', 'x-systemd.before=display-manager.service'}
EARLY_MOUNT = 'x-systemd.before=local-fs.target'
INTERNAL_TRANSPORTS = {'ata', 'sata', 'nvme'}
MICROSOFT_BASIC_DATA = 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'
NO_DEFAULT_DRIVE_LETTER = '0x8000000000000000'
DATA_PARTITIONS = {
    '0x6', '0x7', '0xb', '0xc', '0xe', '0x83',
    MICROSOFT_BASIC_DATA,
    '0fc63daf-8483-4772-8e79-3d69d8477de4',  # Linux filesystem
}
FILESYSTEMS = {
    'ntfs': 'ntfs3', 'ntfs3': 'ntfs3', 'exfat': 'exfat', 'vfat': 'vfat',
    'ext2': 'ext2', 'ext3': 'ext3', 'ext4': 'ext4', 'xfs': 'xfs', 'btrfs': 'btrfs',
}
UUID_PATTERN = re.compile(r'[0-9a-fA-F]+(?:-[0-9a-fA-F]+)*')


def device_nodes(devices):
    for device in devices:
        yield device
        yield from device_nodes(device.get('children') or [])


def device_path(name):
    return os.path.realpath(name) if name and name.startswith('/dev/') else None


def devices_by_uuid(devices):
    groups = defaultdict(set)
    for node in devices:
        if node.get('uuid') and (path := device_path(node.get('name'))):
            groups[node['uuid'].lower()].add(path)
    return groups


def data_target(target):
    return bool(target and (target in ('/mnt', '/media')
                            or target.startswith(('/mnt/', '/media/', '/run/media/'))))


def mountpoints(device):
    return [target for target in device.get('mountpoints') or [] if target]


def system_target(target):
    # Swap is protected by filesystem type; it need not exclude a data sibling.
    return bool(target and target.startswith('/') and not data_target(target))


def fstab_path(path):
    return path.replace('\\', r'\134').replace(' ', r'\040').replace('\t', r'\011')


def supported_partition(partition):
    parttype = (partition.get('parttype') or '').lower()
    if (partition.get('type') != 'part' or parttype not in DATA_PARTITIONS
            or partition.get('children')):
        return False
    flags = str(partition.get('partflags') or '').lower()
    if re.fullmatch(r'(?:0x)?0*', flags):
        return True
    # Linux mounts by path and need not apply a Windows drive letter policy.
    # Other GPT attributes, including combinations with this bit, stay excluded.
    return (parttype == MICROSOFT_BASIC_DATA
            and partition.get('fstype') in ('ntfs', 'ntfs3', 'exfat')
            and flags == NO_DEFAULT_DRIVE_LETTER)


def managed_rows(text):
    marked = False
    for number, line in enumerate(text.splitlines(keepends=True)):
        if line.rstrip('\n') == MARKER:
            marked = True
        elif line.rstrip('\n') == END_MARKER:
            marked = False
        if not marked or not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split()
        if len(fields) != 6:
            continue
        source, target, filesystem, options, dump, check = fields
        uuid = source.removeprefix('UUID=')
        options = set(options.split(','))
        if (source != 'UUID=' + uuid or not UUID_PATTERN.fullmatch(uuid)
                or not (target == '/mnt/callas-' + uuid.lower()
                        or (re.fullmatch(r'/run/media/[a-z_][a-z0-9_-]*/[^/]+', target)
                            and target.rsplit('/', 1)[-1] not in ('.', '..')))
                or filesystem not in FILESYSTEMS.values() or dump != '0' or check not in ('0', '2')
                or not MANAGED_OPTIONS <= options or 'noauto' in options):
            continue
        yield number, fields


def refresh_managed_fstab(previous):
    text = previous.decode('utf-8', errors='surrogateescape')
    lines = text.splitlines(keepends=True)
    for number, fields in managed_rows(text):
        options = fields[3].split(',')
        additions = []
        if EARLY_MOUNT not in options and not any(item.startswith('x-systemd.after=local-fs.target') for item in options):
            additions.append(EARLY_MOUNT)
        if fields[2] == 'ext4':
            if not any(item.startswith('errors=') for item in options):
                additions.append('errors=remount-ro')
            if 'ro' not in options:
                fields[5] = '2'
        if additions or fields[-1] != lines[number].split()[-1]:
            fields[3] = ','.join(options + additions)
            ending = '\n' if lines[number].endswith('\n') else ''
            lines[number] = '\t'.join(fields) + ending
    return ''.join(lines).encode('utf-8', errors='surrogateescape')


def sync_directory(path):
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def plan_mounts(disks, root_source, configured, user, uid, gid, available_target, *, report=None):
    """Return new fstab entries without changing existing mounts."""
    def skipped(device, reason):
        if report:
            report(f"Montagem automática: {device.get('name') or 'dispositivo'}: {reason}.")

    root_device = device_path(root_source)
    devices = list(device_nodes(disks))
    if not root_device or not any(device_path(node.get('name')) == root_device for node in devices):
        if report:
            report('Montagem automática: não foi possível identificar com segurança o disco do sistema.')
        return []

    configured_devices = set()
    protected_devices = {root_device}
    targets = set()
    for entry in configured:
        target = entry.get('target')
        targets.add(target)
        sources = [entry.get('source'), *(entry.get('sources') or [])]
        paths = {path for source in sources if (path := device_path(source))}
        configured_devices.update(paths)
        if system_target(target):
            protected_devices.update(paths)
    configured_uuids = {
        source[5:].lower() for entry in configured
        if (source := entry.get('source') or '').startswith('UUID=')
    }
    protected_uuids = {
        node['uuid'].lower() for node in devices if node.get('uuid')
        and (device_path(node.get('name')) in protected_devices
             or any(system_target(target) for target in mountpoints(node)))
    }
    # A device may be shown under several parents, such as a RAID array.
    # Count distinct devices so repeated references to one are not mistaken for clones.
    uuids = devices_by_uuid(devices)
    entries = []
    desktop_parent = Path('/run/media') / user
    for disk in disks:
        if disk.get('type') != 'disk':
            continue
        if (disk.get('tran') not in INTERNAL_TRANSPORTS or disk.get('ro') is not False
                or disk.get('rm') is not False):
            skipped(disk, 'transporte, mídia removível ou modo somente leitura fora do escopo')
            continue
        # PCIe/SATA controllers can advertise hot-plug for internal disks.
        if any(device_path(node.get('name')) in protected_devices
               or (node.get('uuid') or '').lower() in protected_uuids
               or any(system_target(target) for target in mountpoints(node))
               for node in device_nodes((disk,))):
            skipped(disk, 'disco vinculado a uma montagem do sistema')
            continue

        children = disk.get('children') or []
        # A filesystem can occupy the entire namespace, with no partition table.
        volumes = children if children or disk.get('pttype') else [disk]
        for volume in volumes:
            if volume is not disk and not supported_partition(volume):
                parttype = volume.get('parttype') or 'sem tipo'
                flags = volume.get('partflags') or 'sem atributos'
                skipped(volume, f'partição excluída pelo tipo, atributos ou camada ({parttype}; {flags})')
                continue
            uuid = volume.get('uuid') or ''
            fstype = volume.get('fstype')
            fs = FILESYSTEMS.get(fstype)
            name = device_path(volume.get('name'))
            if not fs or not name or volume.get('ro') is not False or volume.get('rm') is True:
                skipped(volume, f'sistema de arquivos não elegível ({fstype or "sem assinatura"})')
                continue
            if (len(uuid) > 64 or not UUID_PATTERN.fullmatch(uuid)
                    or len(uuids[uuid.lower()]) != 1):
                skipped(volume, 'UUID ausente, inválido ou compartilhado por mais de um dispositivo')
                continue
            if uuid.lower() in configured_uuids or name in configured_devices:
                skipped(volume, 'montagem já configurada')
                continue

            mounts = mountpoints(volume)
            if mounts:
                # Keep the Dolphin/UDisks path when it is already being used,
                # especially if a Steam library was registered there.
                if (len(mounts) != 1 or Path(mounts[0]).parent != desktop_parent
                        or any(ord(char) < 32 and char != '\t' for char in mounts[0])):
                    skipped(volume, 'montagem ativa em outro caminho')
                    continue
                target = mounts[0]
            else:
                target = '/mnt/callas-' + uuid.lower()
            if target in targets or not available_target(target, bool(mounts)):
                skipped(volume, 'ponto de montagem ocupado ou inseguro')
                continue
            options = [
                'nosuid', 'nodev', 'nofail', 'x-systemd.device-timeout=10s',
                'x-systemd.mount-timeout=15s', 'x-systemd.before=display-manager.service', EARLY_MOUNT,
            ]
            if fs in ('ntfs3', 'exfat', 'vfat'):
                options.extend((f'uid={uid}', f'gid={gid}', 'umask=0077'))
            if fs == 'ext4':
                options.append('errors=remount-ro')
            check = 2 if fs == 'ext4' else 0
            entries.append((target, f'UUID={uuid}\t{fstab_path(target)}\t{fs}\t{",".join(options)}\t0\t{check}'))
            targets.add(target)
    return entries


def protected_directory(path):
    info = path.lstat()
    return stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022


def available_target(target, mounted):
    path = Path(target)
    try:
        if not all(protected_directory(parent) for parent in path.parents):
            return False
        if mounted:
            return not path.is_symlink() and path.is_mount()
        if not os.path.lexists(path):
            return True
        # An empty root-owned destination can remain after an interrupted run.
        return protected_directory(path) and not path.is_mount() and not any(path.iterdir())
    except OSError:
        return False


def inventory(*args):
    result = subprocess.run(args, check=True, stdout=subprocess.PIPE, text=True)
    return json.loads(result.stdout)


def verify_candidate(candidate):
    # Existing optional mounts can be disconnected when applying the Update.
    # Keep unrelated preexisting diagnostics, while rejecting parse errors or
    # any new diagnostic in the complete table.
    def check(path):
        return subprocess.run(
            ['findmnt', '--verify', '--tab-file', str(path)],
            env={**os.environ, 'LC_ALL': 'C'}, capture_output=True, text=True,
        )

    result = check(candidate)
    if not result.returncode:
        return
    original = check(FSTAB)
    if (result.returncode == original.returncode
            and result.stdout == original.stdout and result.stderr == original.stderr
            and re.search(r'^0 parse errors,', result.stderr, re.M)):
        print('Montagem automática: diagnósticos preexistentes do fstab preservados.')
        return
    print(result.stdout + result.stderr, file=sys.stderr, end='')
    result.check_returncode()


def mount_unit(target):
    return subprocess.check_output(
        ['systemd-escape', '--path', '--suffix=mount', '--', target], text=True,
    ).strip()


def disk_inventory():
    return inventory('lsblk', '--json', '--paths', '--tree', '-o',
                     'NAME,TYPE,TRAN,RM,RO,HOTPLUG,FSTYPE,UUID,PTTYPE,PARTTYPE,PARTFLAGS,MOUNTPOINTS')['blockdevices']


def recover_ntfs():
    """Offer readable files after a failed normal NTFS mount, without force or repair."""
    rows = [fields for _, fields in managed_rows(FSTAB.read_text(encoding='utf-8', errors='surrogateescape'))
            if fields[2] == 'ntfs3']
    if not rows:
        return
    devices = devices_by_uuid(device_nodes(disk_inventory()))
    active = inventory('findmnt', '--kernel', '--json', '--list', '--nofsroot',
                       '-o', 'SOURCE,TARGET')['filesystems']
    active_sources = {device_path(item['source']) for item in active}
    targets = {item['target'] for item in active}
    for source, escaped, _, options, _, _ in rows:
        uuid = source[5:]
        target = re.sub(r'\\(040|011|134)', lambda match: chr(int(match[1], 8)), escaped)
        alias = '/dev/disk/by-uuid/' + uuid
        path = device_path(alias)
        if (devices.get(uuid.lower()) != {path} or path in active_sources or target in targets
                or not available_target(target, False)):
            continue
        unit = mount_unit(target)
        if subprocess.run(['systemctl', 'is-failed', '--quiet', '--', unit]).returncode:
            continue
        permissions = [item for item in options.split(',')
                       if item in ('noexec', 'nosymfollow')
                       or re.fullmatch(r'(?:uid|gid)=[0-9]+|(?:umask|fmask|dmask)=[0-7]{1,4}', item)]
        print(f'Montagem automática: {target} recusou a montagem normal. Tentando acesso somente leitura.', flush=True)
        try:
            subprocess.run(['mount', '-t', 'ntfs3', '-o', ','.join(('ro', 'nosuid', 'nodev', *permissions)),
                            '--', alias, target], check=True, timeout=12)
        except (OSError, subprocess.SubprocessError) as error:
            print(f'Montagem automática: {target} requer diagnóstico do NTFS ou do disco: {error}', file=sys.stderr)
        else:
            active_sources.add(path)
            targets.add(target)
            print(f'Montagem automática: {target} disponível somente leitura. '
                  'O próximo boot tentará a montagem normal novamente.', flush=True)


def start_mounts(mounts):
    """Activate only selected, still-unmounted data volumes in the live OS."""
    if not mounts or not Path('/run/systemd/system').is_dir():
        return
    if subprocess.run(['systemd-detect-virt', '--chroot', '--quiet']).returncode == 0:
        return
    active = inventory('findmnt', '--kernel', '--json', '--list', '--nofsroot',
                       '-o', 'SOURCE,TARGET')['filesystems']
    active_sources = {device_path(item['source']) for item in active}
    occupied = {item['target'] for item in active}
    pending = {target: source for target, source in mounts.items()
               if source and source not in active_sources and target not in occupied
               and available_target(target, False)}
    if not pending:
        return
    if subprocess.run(['systemctl', 'daemon-reload']).returncode:
        print('Montagem automática: a configuração será ativada no próximo boot.')
        return
    for target in pending:
        unit = mount_unit(target)
        result = subprocess.run(['systemctl', 'start', '--', unit])
        if result.returncode:
            print(f'Montagem automática: falha ao montar {target} nesta sessão. '
                  f'Consulte journalctl -u {unit}; a entrada permanece no fstab.')
        else:
            print(f'Montagem automática ativa em {target}.')


def managed_mounts(configured, sources):
    """Find the UUID-based destinations generated by 3.18.0 or this release."""
    base_options = {'nosuid', 'nodev', 'nofail', 'x-systemd.device-timeout=10s',
                    'x-systemd.before=display-manager.service'}
    result = {}
    for entry in configured:
        source = device_path(entry.get('source'))
        target = entry.get('target')
        uuid = target.removeprefix('/mnt/callas-') if target else ''
        options = set((entry.get('options') or '').split(','))
        if (source and UUID_PATTERN.fullmatch(uuid) and target == '/mnt/callas-' + uuid
                and sources.get(uuid) == {source}
                and base_options <= options and 'noauto' not in options):
            result[target] = source
    return result


def apply(user, live=False):
    account = pwd.getpwnam(user)
    if os.geteuid() != 0 or not account.pw_uid:
        raise ValueError('Requer root e uma conta de usuário normal.')
    original = FSTAB.lstat()
    if (not stat.S_ISREG(original.st_mode) or original.st_uid != 0
            or original.st_mode & 0o022):
        raise ValueError('/etc/fstab deve ser um arquivo regular protegido.')
    previous = FSTAB.read_bytes()

    root_mount = inventory('findmnt', '--kernel', '--json', '--list', '--nofsroot',
                           '--target', '/', '-o', 'SOURCE,TARGET')['filesystems']
    root_source = next((item['source'] for item in root_mount if item['target'] == '/'), None)
    disks = disk_inventory()
    configured = inventory('findmnt', '--fstab', '--evaluate', '--json', '--list',
                           '-o', 'SOURCE,SOURCES,TARGET,OPTIONS')['filesystems']
    entries = plan_mounts(disks, root_source, configured, user, account.pw_uid,
                          account.pw_gid, available_target, report=print)
    sources = devices_by_uuid(device_nodes(disks))
    mounts = managed_mounts(configured, sources) if live else {}
    updated = refresh_managed_fstab(previous)
    if not entries and updated == previous:
        print('Montagem automática: nenhuma nova partição de dados elegível.')
        if live:
            start_mounts(mounts)
        return

    created = []
    committed = False
    try:
        for target, _ in entries:
            path = Path(target)
            if not path.exists():
                path.mkdir(mode=0o700)
                created.append(path)
                path.chmod(0o755)
                sync_directory(path)
                sync_directory(path.parent)
        if entries:
            separator = b'' if not updated or updated.endswith(b'\n') else b'\n'
            addition = MARKER + '\n' + ''.join(line + '\n' for _, line in entries) + END_MARKER + '\n'
            updated += separator + addition.encode('utf-8')
        with tempfile.NamedTemporaryFile(dir=FSTAB.parent, prefix='.fstab.callas-',
                                         delete=False) as staged:
            temporary = Path(staged.name)
            try:
                os.fchown(staged.fileno(), original.st_uid, original.st_gid)
                os.fchmod(staged.fileno(), stat.S_IMODE(original.st_mode))
                staged.write(updated)
                staged.flush()
                os.fsync(staged.fileno())
                verify_candidate(temporary)
                current = FSTAB.lstat()
                if ((current.st_dev, current.st_ino, current.st_ctime_ns)
                        != (original.st_dev, original.st_ino, original.st_ctime_ns)
                        or FSTAB.read_bytes() != previous):
                    raise RuntimeError('/etc/fstab mudou durante a atualização; reaplique a etapa.')
                os.replace(temporary, FSTAB)
                committed = True
                sync_directory(FSTAB.parent)
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        if not committed:
            for path in reversed(created):
                with suppress(OSError):
                    path.rmdir()
    for target, row in entries:
        print(f'Montagem no boot configurada em {target}.')
        if live:
            uuid = row.split('\t', 1)[0].removeprefix('UUID=').lower()
            mounts[target] = next(iter(sources[uuid]))
    if live:
        start_mounts(mounts)


@contextmanager
def disk_configuration_lock():
    fd = os.open('/run/callas-disk-configuration.lock',
                 os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_RDWR, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise RuntimeError('O arquivo de bloqueio da configuração dos discos não está protegido.')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def main(args):
    if os.geteuid() != 0:
        raise ValueError('Esta operação requer root.')
    with disk_configuration_lock():
        if args == ['--recover-ntfs']:
            recover_ntfs()
        elif len(args) == 1:
            apply(args[0])
        elif len(args) == 2 and args[1] in ('--live', '--manual'):
            username = args[0]
            if args[1] == '--manual':
                if username != os.environ.get('SUDO_USER'):
                    raise ValueError('Abra a ferramenta de armazenamento pela sua conta na Central.')
                subprocess.run(['/usr/local/libexec/callas-storage', '--config', username], check=True)
            apply(username, live=True)
            recover_ntfs()
        else:
            raise ValueError('Uso interno: callas-automount USUARIO [--live|--manual]')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Montagem automática: {error}', file=sys.stderr)
        sys.exit(1)
