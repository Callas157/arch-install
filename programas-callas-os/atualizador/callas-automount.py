#!/usr/bin/python3
"""Prepare boot mounts for local secondary data partitions."""
from collections import Counter
from contextlib import suppress
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
INTERNAL_TRANSPORTS = {'ata', 'sata', 'nvme'}
DATA_PARTITIONS = {
    '0x7', '0x83',
    'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7',  # Microsoft basic data
    '0fc63daf-8483-4772-8e79-3d69d8477de4',  # Linux filesystem
}
FILESYSTEMS = {'ntfs': 'ntfs3', 'exfat': 'exfat', 'ext4': 'ext4'}
UUID_PATTERN = re.compile(r'[0-9a-fA-F]+(?:-[0-9a-fA-F]+)*')


def device_nodes(devices):
    for device in devices:
        yield device
        yield from device_nodes(device.get('children') or [])


def device_path(name):
    return os.path.realpath(name) if name and name.startswith('/dev/') else None


def data_target(target):
    return bool(target and target.startswith(('/mnt/', '/media/', '/run/media/')))


def fstab_path(path):
    return path.replace('\\', r'\134').replace(' ', r'\040').replace('\t', r'\011')


def supported_partition(partition):
    parttype = (partition.get('parttype') or '').lower()
    return (partition.get('type') == 'part' and parttype in DATA_PARTITIONS
            and partition.get('partflags') in (None, '', '0x0')
            and not partition.get('children'))


def plan_mounts(disks, root_source, configured, user, uid, gid, available_target):
    """Return new fstab entries without changing existing mounts."""
    root_device = device_path(root_source)
    devices = list(device_nodes(disks))
    if not root_device or not any(device_path(node.get('name')) == root_device for node in devices):
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
        if not data_target(target):
            protected_devices.update(paths)
    configured_uuids = {
        source[5:].lower() for entry in configured
        if (source := entry.get('source') or '').startswith('UUID=')
    }
    uuid_counts = Counter((node.get('uuid') or '').lower() for node in devices)
    entries = []
    desktop_parent = Path('/run/media') / user
    for disk in disks:
        partitions = disk.get('children') or []
        if (disk.get('type') != 'disk' or disk.get('tran') not in INTERNAL_TRANSPORTS
                or any(disk.get(flag) is not False for flag in ('ro', 'rm', 'hotplug'))
                or not partitions or not all(supported_partition(part) for part in partitions)):
            continue
        if any(device_path(node.get('name')) in protected_devices
               or any(target and not data_target(target) for target in node.get('mountpoints') or [])
               for node in (disk, *partitions)):
            continue

        for partition in partitions:
            uuid = partition.get('uuid') or ''
            fs = FILESYSTEMS.get(partition.get('fstype'))
            name = device_path(partition.get('name'))
            if (not fs or not name or partition.get('ro') is not False
                    or len(uuid) > 64 or not UUID_PATTERN.fullmatch(uuid)
                    or uuid_counts[uuid.lower()] != 1 or uuid.lower() in configured_uuids
                    or name in configured_devices):
                continue

            mounts = [target for target in partition.get('mountpoints') or [] if target]
            if mounts:
                # Keep the Dolphin/UDisks path when it is already being used,
                # especially if a Steam library was registered there.
                if (len(mounts) != 1 or Path(mounts[0]).parent != desktop_parent
                        or any(ord(char) < 32 and char != '\t' for char in mounts[0])):
                    continue
                target = mounts[0]
            else:
                target = '/mnt/callas-' + uuid.lower()
            if target in targets or not available_target(target, bool(mounts)):
                continue
            options = [
                'nosuid', 'nodev', 'nofail', 'x-systemd.device-timeout=10s',
                'x-systemd.mount-timeout=15s', 'x-systemd.before=display-manager.service',
            ]
            if fs in ('ntfs3', 'exfat'):
                options.extend((f'uid={uid}', f'gid={gid}', 'umask=0077'))
            entries.append((target, f'UUID={uuid}\t{fstab_path(target)}\t{fs}\t{",".join(options)}\t0\t0'))
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


def apply(user):
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
    disks = inventory('lsblk', '--json', '--paths', '--tree', '-o',
                      'NAME,TYPE,TRAN,RM,RO,HOTPLUG,FSTYPE,UUID,PARTTYPE,PARTFLAGS,MOUNTPOINTS')['blockdevices']
    configured = inventory('findmnt', '--fstab', '--evaluate', '--json', '--list',
                           '-o', 'SOURCE,SOURCES,TARGET')['filesystems']
    entries = plan_mounts(disks, root_source, configured, user, account.pw_uid,
                          account.pw_gid, available_target)
    if not entries:
        print('Montagem automática: nenhuma nova partição de dados elegível.')
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
        separator = b'' if not previous or previous.endswith(b'\n') else b'\n'
        addition = '# Montagem de discos de dados — Callas OS\n'
        addition += ''.join(line + '\n' for _, line in entries)
        with tempfile.NamedTemporaryFile(dir=FSTAB.parent, prefix='.fstab.callas-',
                                         delete=False) as staged:
            temporary = Path(staged.name)
            try:
                os.fchown(staged.fileno(), original.st_uid, original.st_gid)
                os.fchmod(staged.fileno(), stat.S_IMODE(original.st_mode))
                staged.write(previous + separator + addition.encode('utf-8'))
                staged.flush()
                os.fsync(staged.fileno())
                subprocess.run(['findmnt', '--verify', '--tab-file', str(temporary)], check=True)
                current = FSTAB.lstat()
                if ((current.st_dev, current.st_ino, current.st_ctime_ns)
                        != (original.st_dev, original.st_ino, original.st_ctime_ns)
                        or FSTAB.read_bytes() != previous):
                    raise RuntimeError('/etc/fstab mudou durante a atualização; reaplique a etapa.')
                os.replace(temporary, FSTAB)
                committed = True
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        if not committed:
            for path in reversed(created):
                with suppress(OSError):
                    path.rmdir()
    for target, _ in entries:
        print(f'Montagem no próximo boot configurada em {target}.')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Uso interno: callas-automount USUARIO')
        apply(sys.argv[1])
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Montagem automática: {error}', file=sys.stderr)
        sys.exit(1)
